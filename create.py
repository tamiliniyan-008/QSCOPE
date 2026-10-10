import os

base = r'c:\Users\Slim5\Documents\q fcous'
files = {}

files['core/config.py'] = """from dataclasses import dataclass, field
from typing import List

@dataclass
class AppConfig:
    mode: str = 'synthetic'
    window_size: int = 60
    baseline_windows: int = 8
    measurement_p0: float = 0.5
    measurement_amplitude: float = 0.5
    measurement_contrast: float = 0.88
    measurement_phi0: float = 0.0
    uncertainty_profile: str = 'wide'
    threshold: float = 0.067349
    cusum_k: float = 0.002
    cusum_h: float = 0.05
    atom_count_default: int = 2000
    shots: int = 2000
    seed: int = 42
    database_path: str = 'atom_qsa.db'
    log_level: str = 'INFO'
    cors_origins: List[str] = field(default_factory=lambda: ['http://localhost:3000'])
    max_upload_size_mb: int = 50
    quantum_enabled: bool = False
    quantum_backend: str = 'auto'
"""

files['modules/data_sources/csv_source.py'] = """import csv
import datetime
from typing import List, Dict, Any
from core.contracts import QualityReport, ProvenanceRecord, DataSource, WindowData

class CSVDataSource(DataSource):
    def __init__(self, csv_path: str = ''):
        self.csv_path = csv_path

    def load(self, config) -> List[Dict[str, Any]]:
        path = self.csv_path or getattr(config, 'csv_path', 'data.csv')
        records = []
        try:
            with open(path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    parsed = {}
                    for k, v in row.items():
                        try:
                            parsed[k] = float(v)
                        except ValueError:
                            parsed[k] = v
                    records.append(parsed)
        except Exception:
            pass
        return records

    def validate_schema(self, records: List[Dict[str, Any]]) -> QualityReport:
        missing = {}
        invalid = {}
        warnings = []
        valid_count = 0
        reqs = ['population', 'phase_rad', 'contrast']
        for r in records:
            valid = True
            for req in reqs:
                if req not in r:
                    missing[req] = missing.get(req, 0) + 1
                    valid = False
                elif not isinstance(r[req], (int, float)):
                    invalid.setdefault(req, []).append(str(r[req]))
                    valid = False
            if valid:
                valid_count += 1

        prov = ProvenanceRecord(
            source_type='unverified', source_id=self.csv_path,
            timestamp=datetime.datetime.utcnow().isoformat(), description='CSV load',
            model_version='1.0', config_version='1.0', warnings=tuple(warnings)
        )
        return QualityReport(
            valid=(valid_count>0), total_records=len(records), missing_fields=missing,
            invalid_values=invalid, warnings=warnings, discarded_records=len(records)-valid_count,
            interpolated_records=0, provenance=prov
        )
"""

files['modules/data_sources/synthetic_source.py'] = """import math
import random
import csv
import datetime
from typing import List, Dict, Any
from core.contracts import QualityReport, ProvenanceRecord, DataSource

class SyntheticDataSource(DataSource):
    def load(self, config) -> List[Dict[str, Any]]:
        random.seed(config.seed)
        records = []
        for i in range(config.window_size * config.baseline_windows):
            phase = random.uniform(0, 2*math.pi)
            pop = config.measurement_p0 + config.measurement_amplitude * config.measurement_contrast * math.cos(phase)
            noise = random.gauss(0, 1.0/math.sqrt(config.shots) if config.shots else 0.05)
            records.append({'phase_rad': phase, 'population': max(0.0, min(1.0, pop+noise)), 'contrast': config.measurement_contrast, 'timestamp': i})
        return records

    def validate_schema(self, records: List[Dict[str, Any]]) -> QualityReport:
        prov = ProvenanceRecord(
            source_type='synthetic', source_id='synth_1', timestamp=datetime.datetime.utcnow().isoformat(),
            description='Synthetic gen', model_version='1.0', config_version='1.0', warnings=()
        )
        return QualityReport(True, len(records), {}, {}, [], 0, 0, prov)
        
    def generate_sample_csv(self, config, filepath: str):
        recs = self.load(config)
        if recs:
            with open(filepath, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=recs[0].keys())
                w.writeheader()
                w.writerows(recs)
"""

files['modules/phase_reconstruction/simulated_reconstructor.py'] = """import math
import statistics
import datetime
from core.contracts import PhaseResult, ProvenanceRecord, PhaseReconstructor, WindowData

class SimulatedReconstructor(PhaseReconstructor):
    def reconstruct(self, window: WindowData, config) -> PhaseResult:
        phases = [r.get('phase_rad', 0.0) for r in window.records]
        if not phases:
            return PhaseResult(0.0, 0.0, 0.0, 'simulated', False, 'No data', (), None)
        mean_p = statistics.mean(phases)
        spread_p = statistics.stdev(phases) if len(phases)>1 else 0.0
        res_u = spread_p / math.sqrt(len(phases)) if len(phases)>0 else 0.0
        prov = ProvenanceRecord(
            source_type='model_derived', source_id='sim_recon',
            timestamp=datetime.datetime.utcnow().isoformat(), description='Sim recon',
            model_version='1.0', config_version='1.0', warnings=()
        )
        return PhaseResult(mean_p, spread_p, res_u, 'simulated', True, '', ('gaussian_noise',), prov)
"""

files['modules/uncertainty/residual_uncertainty.py'] = """import statistics
from core.contracts import UncertaintyEstimator, PhaseResult, WindowData, UncertaintyEnvelope

class ResidualUncertainty(UncertaintyEstimator):
    def estimate(self, phase_result: PhaseResult, window: WindowData, config) -> UncertaintyEnvelope:
        c_vals = [r.get('contrast', config.measurement_contrast) for r in window.records if 'contrast' in r]
        c = statistics.median(c_vals) if c_vals else config.measurement_contrast
        return UncertaintyEnvelope(
            mean=phase_result.phase_mean_rad,
            variance=phase_result.phase_spread_rad**2,
            regimes=[], valid=True, method='residual', reason=''
        )
"""

files['modules/uncertainty/distribution_models.py'] = """import math

def gaussian_phase_moments(mu: float, sigma: float):
    var2 = sigma**2
    e_cos = math.cos(mu) * math.exp(-var2 / 2.0)
    e_cos2 = 0.5 * (1.0 + math.cos(2.0*mu) * math.exp(-2.0*var2))
    var_cos = max(0.0, e_cos2 - e_cos**2)
    return e_cos, var_cos

def uniform_phase_moments(a: float, b: float):
    diff = b - a
    if diff == 0: return math.cos(a), 0.0
    e_cos = (math.sin(b) - math.sin(a)) / diff
    e_cos2 = 0.5 * (1.0 + (math.sin(2.0*b) - math.sin(2.0*a)) / (2.0*diff))
    var_cos = max(0.0, e_cos2 - e_cos**2)
    return e_cos, var_cos
"""

files['modules/uncertainty/propagation.py'] = """import math

def propagate_uncertainty(val: float, err: float, func):
    pass
"""

files['modules/measurement_models/fringe_model.py'] = """import math
from typing import Dict, Any
from core.contracts import MeasurementModel, MeasurementModelResult

class FringeModel(MeasurementModel):
    def predict(self, phase_rad: float, contrast: float, offset: float, atom_count: int) -> MeasurementModelResult:
        pop = offset + 0.5 * contrast * math.cos(phase_rad)
        var = pop * (1.0 - pop) / atom_count if atom_count > 0 else 0.0
        return MeasurementModelResult(
            expected_population=pop, population_variance=var, linear_approximation=pop,
            nonlinear_vs_linear_discrepancy=0.0, model_version='1.0', valid=True,
            parameters={'contrast': contrast, 'offset': offset, 'atom_count': float(atom_count)}, reason=''
        )
        
    def predict_distribution(self, envelope, config) -> MeasurementModelResult:
        return MeasurementModelResult(0.5, 0.01, 0.5, 0.0, '1.0', True, {}, '')
"""

files['modules/estimators/ekf_estimator.py'] = """import math
import datetime
from typing import Dict, Any
from core.contracts import StateEstimator, EstimatorResult, WindowData, MeasurementModel, ProvenanceRecord

class EKFEstimator(StateEstimator):
    def estimate(self, window: WindowData, model: MeasurementModel, config) -> EstimatorResult:
        if not window.records:
            return EstimatorResult(0.0, 0.0, 'ekf', False, {}, 'no data', None)
        
        mu = 0.0
        P = 1.0
        for r in window.records:
            phase = r.get('phase_rad', 0.0)
            pop = r.get('population', 0.5)
            H = -0.5 * config.measurement_contrast * math.sin(mu)
            S = H * P * H + (0.5 * 0.5 / config.shots) if config.shots > 0 else 1.0
            K = (P * H) / S if S != 0 else 0
            y = pop - (config.measurement_p0 + 0.5 * config.measurement_contrast * math.cos(mu))
            mu = mu + K * y
            P = (1.0 - K * H) * P
            
        prov = ProvenanceRecord('model_derived', 'ekf_1', datetime.datetime.utcnow().isoformat(), 'EKF', '1.0', '1.0', ())
        return EstimatorResult(mu, math.sqrt(max(0, P)), 'ekf', True, {}, '', prov)
"""

files['modules/estimators/phase_grid_estimator.py'] = """from core.contracts import StateEstimator, EstimatorResult, WindowData, MeasurementModel

class PhaseGridEstimator(StateEstimator):
    def estimate(self, window: WindowData, model: MeasurementModel, config) -> EstimatorResult:
        return EstimatorResult(0.0, 0.0, 'grid', True, {}, '', None)
"""

files['modules/risk_certificates/dmean_certificate.py'] = """import math
from typing import Dict, Any
from core.contracts import RiskCertificatePlugin, RiskCertificate

class DMeanCertificate(RiskCertificatePlugin):
    def evaluate(self, model_result, estimator_result, envelope, config) -> RiskCertificate:
        mu = estimator_result.phase_estimate_rad
        sigma = estimator_result.uncertainty_rad
        p0 = config.measurement_p0
        A = config.measurement_amplitude
        C = config.measurement_contrast
        N = config.shots

        var2 = sigma**2
        e_cos = math.cos(mu) * math.exp(-var2 / 2.0)
        e_cos2 = 0.5 * (1.0 + math.cos(2.0*mu) * math.exp(-2.0*var2))
        var_cos = max(0.0, e_cos2 - e_cos**2)

        e_p_phi = p0 + A * C * e_cos
        p_mu = p0 + A * C * math.cos(mu)
        var_p_phi = (A * C)**2 * var_cos

        denom = math.sqrt(var_p_phi + 1.0/(4.0*N)) if N > 0 else math.sqrt(var_p_phi)
        B = abs(e_p_phi - p_mu) / denom if denom > 0 else 0.0

        return RiskCertificate(
            score_name='dmean', score_value=B, score_lower=B*0.9, score_upper=B*1.1,
            inputs={'mu': mu, 'sigma': sigma}, assumptions=('gaussian',), limits=(),
            model_version='1.0', valid=True, sensitivity={}, data_quality_status='ok',
            warnings=(), reason=''
        )
"""

files['modules/decision_policies/three_state_policy.py'] = """from core.contracts import DecisionPolicy, DecisionResult, RiskCertificate, EstimatorResult

class ThreeStatePolicy(DecisionPolicy):
    def decide(self, certificate: RiskCertificate, config) -> DecisionResult:
        state = 'STAY_EKF'
        if certificate.score_value > config.threshold:
            state = 'ESCALATE_NONLINEAR'
        return DecisionResult(state, 'measure', certificate, config.threshold, config.uncertainty_profile, 'eval', None, ())
        
    def confirm_escalation(self, decision: DecisionResult, estimator_result: EstimatorResult) -> DecisionResult:
        return DecisionResult(
            decision.state, decision.next_action, decision.certificate, decision.threshold,
            decision.profile, decision.explanation, estimator_result, decision.warnings
        )
"""

files['modules/risk_certificates/envelope_evaluator.py'] = """class EnvelopeEvaluator:
    def evaluate(self, envelope):
        pass
"""

files['modules/monitoring/cusum_monitor.py'] = """from core.contracts import HealthMonitor, HealthRecord, WindowData, ProvenanceRecord
import datetime

class CUSUMMonitor(HealthMonitor):
    def __init__(self):
        self.score = 0.0
        
    def update(self, window: WindowData, features: dict, config) -> HealthRecord:
        k = config.cusum_k
        h = config.cusum_h
        val = features.get('fidelity_loss', 0.0)
        self.score = max(0.0, self.score + val - k)
        alert = self.score > h
        prov = ProvenanceRecord('model_derived', 'cusum_1', datetime.datetime.utcnow().isoformat(), 'cusum', '1.0', '1.0', ())
        return HealthRecord(self.score, h, alert, features, 1.0-val, val, prov, ())
        
    def reset(self):
        self.score = 0.0
"""

files['modules/monitoring/feature_extractor.py'] = """import statistics

class FeatureExtractor:
    def extract(self, window):
        return {'fidelity_loss': 0.01}
"""

files['modules/monitoring/health_monitor.py'] = """class HealthMonitorManager:
    pass
"""

for path, content in files.items():
    full_path = os.path.join(base, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

print('All files created successfully.')
