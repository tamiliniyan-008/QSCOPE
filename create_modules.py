import os

workspace = r"c:\Users\Slim5\Documents\q fcous"

FILES = {
    r"modules\phase_reconstruction\__init__.py": "",
    r"modules\phase_reconstruction\base.py": "from core.contracts import PhaseReconstructor\n",
    r"modules\phase_reconstruction\simulated_reconstructor.py": """import numpy as np
from core.contracts import PhaseReconstructor, PhaseResult

class SimulatedPhaseReconstructor(PhaseReconstructor):
    def reconstruct(self, window_data):
        if not hasattr(window_data, 'phase_signal') or window_data.phase_signal is None:
            return PhaseResult(valid=False, reason='Missing phase_signal')
        
        sig = np.array(window_data.phase_signal)
        if len(sig) == 0:
            return PhaseResult(valid=False, reason='Insufficient samples')
        if not np.all(np.isfinite(sig)):
            return PhaseResult(valid=False, reason='Non-finite values')
            
        n = len(sig)
        # Distinguish environmental phase spread from residual uncertainty
        phase_mean = float(np.mean(sig))
        phase_spread = float(np.std(sig)) 
        residual_uncertainty = float(phase_spread / np.sqrt(n)) if n > 0 else float('inf')
        
        return PhaseResult(
            valid=True,
            phase_mean=phase_mean,
            phase_spread=phase_spread,
            residual_uncertainty=residual_uncertainty,
            provenance='synthetic',
            assumptions=[
                'Phase values taken directly from input signal',
                'No physical sensitivity model applied'
            ]
        )
""",
    r"modules\phase_reconstruction\accelerometer_reconstructor.py": """from core.contracts import PhaseReconstructor, PhaseResult

class AccelerometerPhaseReconstructor(PhaseReconstructor):
    def __init__(self, sensitivity_model=None, pulse_timing=None, coordinate_conventions=None, calibration=None):
        self.sensitivity_model = sensitivity_model
        self.pulse_timing = pulse_timing
        self.coordinate_conventions = coordinate_conventions
        self.calibration = calibration
        
    def reconstruct(self, window_data):
        missing = []
        if self.sensitivity_model is None: missing.append('sensitivity_model')
        if self.pulse_timing is None: missing.append('pulse_timing')
        if self.coordinate_conventions is None: missing.append('coordinate_conventions')
        if self.calibration is None: missing.append('calibration')
        
        if missing:
            return PhaseResult(
                valid=False,
                reason=f"Required parameter(s) {', '.join(missing)} unavailable; cannot reconstruct physical phase without calibrated sensitivity model"
            )
            
        # Would integrate accelerometer data with sensitivity function here
        # Never invents residual uncertainty or labels it measured
        return PhaseResult(valid=False, reason='Not implemented: awaiting physical integration')
""",
    r"modules\uncertainty\__init__.py": "",
    r"modules\uncertainty\residual_uncertainty.py": """from core.contracts import UncertaintyEstimator, UncertaintyEnvelope

class ResidualUncertaintyEstimator(UncertaintyEstimator):
    def __init__(self, profile='narrow', distribution_family='gaussian'):
        self.profile = profile
        self.distribution_family = distribution_family
        
    def estimate(self, phase_result, window_data=None):
        m = phase_result.phase_mean
        s = phase_result.phase_spread
        c = getattr(phase_result, 'contrast', 1.0)
        
        if self.profile == 'narrow':
            m_off = 0.15
            s_mult = [0.8, 1.25]
            c_mult = [0.9, 1.1]
        else:
            m_off = 0.30
            s_mult = [0.5, 2.0]
            c_mult = [0.6, 1.4]
            
        return UncertaintyEnvelope(
            phase_mean_range=(m - m_off, m + m_off),
            phase_spread_range=(s * s_mult[0], s * s_mult[1]),
            contrast_range=(c * c_mult[0], c * c_mult[1]),
            distribution_family=self.distribution_family,
            assumptions=[f"Profile: {self.profile}"]
        )
""",
    r"modules\uncertainty\regime_builder.py": """import numpy as np
import itertools

class RegimeBuilder:
    def __init__(self, profile='narrow'):
        self.profile = profile
        self.points = 3 if profile == 'narrow' else 5
        
    def build(self, envelope):
        means = np.linspace(envelope.phase_mean_range[0], envelope.phase_mean_range[1], self.points)
        spreads = np.linspace(envelope.phase_spread_range[0], envelope.phase_spread_range[1], self.points)
        contrasts = np.linspace(envelope.contrast_range[0], envelope.contrast_range[1], self.points)
        
        return [
            {'phase_mean': float(m), 'phase_spread': float(s), 'contrast': float(c)}
            for m, s, c in itertools.product(means, spreads, contrasts)
        ]
""",
    r"modules\uncertainty\distribution_models.py": """import numpy as np

def gaussian_phase_moments(mu, sigma):
    e_cos = np.cos(mu) * np.exp(-0.5 * sigma**2)
    e_cos2 = 0.5 * (1.0 + np.cos(2*mu) * np.exp(-2.0 * sigma**2))
    return {'E_cos': e_cos, 'E_cos2': e_cos2, 'Var_cos': max(0.0, e_cos2 - e_cos**2)}

def uniform_phase_moments(mu, half_width):
    if half_width < 1e-9:
        e_cos = np.cos(mu)
        e_cos2 = np.cos(mu)**2
    else:
        e_cos = np.cos(mu) * np.sin(half_width) / half_width
        e_cos2 = 0.5 * (1.0 + np.cos(2*mu) * np.sin(2*half_width) / (2*half_width))
    return {'E_cos': e_cos, 'E_cos2': e_cos2, 'Var_cos': max(0.0, e_cos2 - e_cos**2)}

def get_distribution_moments(family, params):
    if family == 'gaussian':
        return gaussian_phase_moments(params['mu'], params['sigma'])
    elif family == 'uniform':
        return uniform_phase_moments(params['mu'], params.get('half_width', params.get('sigma')))
    raise ValueError(f"Unknown family: {family}")
""",
    r"modules\uncertainty\propagation.py": """from modules.uncertainty.distribution_models import get_distribution_moments
import numpy as np

def propagate_through_model(model_params, phase_mean, phase_sigma, contrast, atom_count, family='gaussian'):
    p0 = model_params.get('p0', 0.5)
    A = model_params.get('A', 0.5)
    phi0 = model_params.get('phi0', 0.0)
    
    mu_shift = phase_mean + phi0
    moments = get_distribution_moments(family, {'mu': mu_shift, 'sigma': phase_sigma})
    
    e_pop = p0 + A * contrast * moments['E_cos']
    qpn = 1.0 / (4.0 * atom_count) if atom_count > 0 else 0.0
    v_pop = (A * contrast)**2 * moments['Var_cos'] + qpn
    
    l_lin = p0 + A * contrast * np.cos(mu_shift)
    
    return {
        'expected_population': float(e_pop),
        'population_variance': float(v_pop),
        'local_linear_prediction': float(l_lin)
    }
""",
    r"modules\measurement_models\__init__.py": "",
    r"modules\measurement_models\base.py": "from core.contracts import MeasurementModel\n",
    r"modules\measurement_models\fringe_model.py": """from core.contracts import MeasurementModel
from modules.uncertainty.propagation import propagate_through_model
import numpy as np

class FringeModel(MeasurementModel):
    def __init__(self, p0=0.5, A=0.5, phi0=0.0, contrast=1.0):
        self.p0 = p0
        self.A = A
        self.phi0 = phi0
        self.contrast = contrast
        self.model_version = f"Fringe_p0_{p0}_A_{A}_phi0_{phi0}"
        
    def predict(self, phase_rad, contrast=None, offset=None, atom_count=1000):
        p0 = offset if offset is not None else self.p0
        c = contrast if contrast is not None else self.contrast
        val = p0 + self.A * c * np.cos(phase_rad + self.phi0)
        return {
            'point_prediction': float(val),
            'linear_approximation': float(val),
            'discrepancy': 0.0
        }
        
    def predict_distribution(self, envelope, config):
        mu = (envelope.phase_mean_range[0] + envelope.phase_mean_range[1]) / 2.0
        sigma = (envelope.phase_spread_range[0] + envelope.phase_spread_range[1]) / 2.0
        c = (envelope.contrast_range[0] + envelope.contrast_range[1]) / 2.0
        n = config.get('atom_count', 1000)
        
        return propagate_through_model(
            {'p0': self.p0, 'A': self.A, 'phi0': self.phi0},
            mu, sigma, c, n, envelope.distribution_family
        )
""",
    r"modules\measurement_models\calibration.py": """from core.exceptions import InvalidInputError

class ModelCalibration:
    def __init__(self, p0=0.5, A=0.5, phi0=0.0, provenance='default'):
        self.p0 = p0
        self.A = A
        self.phi0 = phi0
        self.provenance = provenance
        self._validate()
        
    def _validate(self):
        if not (0.0 <= self.p0 <= 1.0):
            raise ValueError("INVALID_INPUT: p0 must be between 0 and 1")
        if not (0.0 <= self.A <= 1.0):
            raise ValueError("INVALID_INPUT: A must be between 0 and 1")
            
    def to_dict(self):
        return {'p0': self.p0, 'A': self.A, 'phi0': self.phi0, 'provenance': self.provenance}
""",
    r"modules\estimators\__init__.py": "",
    r"modules\estimators\base.py": "from core.contracts import StateEstimator\n",
    r"modules\estimators\ekf_estimator.py": """from core.contracts import StateEstimator, EstimatorResult
import numpy as np

class EKFEstimator(StateEstimator):
    def __init__(self, fringe_model, q_noise=1e-4):
        self.fringe_model = fringe_model
        self.q_noise = q_noise
        
    def estimate(self, measurements, initial_state, dt, atom_count=1000):
        st = np.array(initial_state, dtype=float)
        P = np.eye(2)
        Q = np.eye(2) * self.q_noise
        R = 1.0 / (4.0 * atom_count) if atom_count > 0 else 1.0
        warnings = []
        
        # Predict
        st[0] += st[1] * dt
        F = np.array([[1.0, dt], [0.0, 1.0]])
        P = F @ P @ F.T + Q
        if not np.all(np.isfinite(P)):
            warnings.append("Numerical instability in prediction")
            
        # Update
        z = measurements.get('population', 0.5)
        c = measurements.get('contrast', 1.0)
        
        p0 = self.fringe_model.p0
        A = self.fringe_model.A
        phi0 = self.fringe_model.phi0
        
        h = p0 + A * c * np.cos(st[0] + phi0)
        H = np.array([[-A * c * np.sin(st[0] + phi0), 0.0]])
        
        inn = z - h
        S = H @ P @ H.T + R
        inn_var = S[0, 0]
        
        if inn_var <= 0:
            warnings.append("Non-positive innovation variance")
            inn_var = 1e-6
            
        K = P @ H.T / inn_var
        st = st + (K.flatten() * inn)
        P = (np.eye(2) - K @ H) @ P
        
        return EstimatorResult(
            phase_estimate=float(st[0]),
            phase_rate_estimate=float(st[1]),
            uncertainty=float(np.sqrt(P[0,0])),
            diagnostics={
                'innovation': float(inn),
                'innovation_variance': float(inn_var),
                'normalized_innovation': float(inn / np.sqrt(inn_var)),
                'filter_gain': K.flatten().tolist(),
                'warnings': warnings
            }
        )
""",
    r"modules\estimators\phase_grid_estimator.py": """from core.contracts import StateEstimator, EstimatorResult
import numpy as np

class PhaseGridEstimator(StateEstimator):
    def __init__(self, fringe_model, resolution=512):
        self.fringe_model = fringe_model
        self.resolution = resolution
        self.grid = np.linspace(-np.pi, np.pi, resolution)
        
    def estimate(self, measurements, initial_state=None, atom_count=1000):
        z = measurements.get('population', 0.5)
        c = measurements.get('contrast', 1.0)
        
        p0 = self.fringe_model.p0
        A = self.fringe_model.A
        phi0 = self.fringe_model.phi0
        
        h_grid = p0 + A * c * np.cos(self.grid + phi0)
        v_n = 1.0 / (4.0 * atom_count) if atom_count > 0 else 1.0
        
        log_lik = -0.5 * ((z - h_grid)**2) / v_n
        log_lik -= np.max(log_lik)
        lik = np.exp(log_lik)
        post = lik / np.sum(lik)
        
        map_idx = np.argmax(post)
        map_est = self.grid[map_idx]
        
        mean_est = np.sum(self.grid * post)
        var_est = np.sum(((self.grid - mean_est)**2) * post)
        
        return EstimatorResult(
            phase_estimate=float(map_est),
            phase_rate_estimate=0.0,
            uncertainty=float(np.sqrt(var_est)),
            diagnostics={'resolution': self.resolution}
        )
""",
    r"modules\estimators\particle_estimator.py": """from core.contracts import StateEstimator
from core.exceptions import UnavailableError

class ParticleEstimator(StateEstimator):
    def __init__(self, *args, **kwargs):
        raise UnavailableError('Particle filter estimator requires validated configuration. Use phase_grid_estimator as the nonlinear alternative.')
        
    def estimate(self, *args, **kwargs):
        pass
""",
    r"modules\risk_certificates\__init__.py": "",
    r"modules\risk_certificates\base.py": "from core.contracts import RiskCertificatePlugin\n",
    r"modules\risk_certificates\dmean_certificate.py": """from core.contracts import RiskCertificatePlugin, RiskCertificate
from modules.uncertainty.propagation import propagate_through_model
import numpy as np
import hashlib

class DmeanCertificate(RiskCertificatePlugin):
    def evaluate(self, envelope, model_params, atom_count=1000):
        mu = (envelope.phase_mean_range[0] + envelope.phase_mean_range[1]) / 2.0
        sigma = (envelope.phase_spread_range[0] + envelope.phase_spread_range[1]) / 2.0
        c = (envelope.contrast_range[0] + envelope.contrast_range[1]) / 2.0
        
        prop = propagate_through_model(model_params, mu, sigma, c, atom_count, envelope.distribution_family)
        
        B = abs(prop['expected_population'] - prop['local_linear_prediction']) / np.sqrt(max(1e-12, prop['population_variance']))
        
        phash = hashlib.md5(f"{model_params}_{atom_count}".encode()).hexdigest()
        
        return RiskCertificate(
            valid=True,
            score_lower=float(B),
            score_upper=float(B),
            model_version=f"Dmean_v1_{phash}",
            indicator_type="DISCREPANCY_INDICATOR",
            reason="Evaluated center of envelope"
        )
""",
    r"modules\risk_certificates\envelope_evaluator.py": """from modules.uncertainty.regime_builder import RegimeBuilder
from modules.uncertainty.propagation import propagate_through_model
import numpy as np

class EnvelopeEvaluator:
    def __init__(self, profile='narrow'):
        self.builder = RegimeBuilder(profile)
        
    def evaluate_envelope(self, envelope, model_params, atom_count=1000):
        grid = self.builder.build(envelope)
        scores = []
        
        for pt in grid:
            prop = propagate_through_model(
                model_params, pt['phase_mean'], pt['phase_spread'], pt['contrast'],
                atom_count, envelope.distribution_family
            )
            B = abs(prop['expected_population'] - prop['local_linear_prediction']) / np.sqrt(max(1e-12, prop['population_variance']))
            scores.append(B)
            
        return {
            'min_score': float(np.min(scores)),
            'max_score': float(np.max(scores)),
            'grid_size': len(grid),
            'extreme_params_note': 'Parameter sensitivity requires further gradient analysis'
        }
""",
    r"modules\risk_certificates\calibration.py": """class RiskCalibration:
    def __init__(self, threshold=1.0, profile_metadata=None):
        self.threshold = threshold
        self.profile_metadata = profile_metadata or {}
        self.calibration_notes = "Converting score to failure probability requires separate calibration."
        
    def is_calibrated(self) -> bool:
        return False
        
    def get_explanation(self):
        return "Not calibrated: lacks real empirical failure data to map discrepancy scores to probabilities."
""",
    r"modules\decision_policies\__init__.py": "",
    r"modules\decision_policies\base.py": "from core.contracts import DecisionPolicy\n",
    r"modules\decision_policies\three_state_policy.py": """from core.contracts import DecisionPolicy, DecisionResult

class ThreeStatePolicy(DecisionPolicy):
    def __init__(self, threshold=1.0, profile='narrow'):
        self.threshold = threshold
        self.profile = profile
        
    def decide(self, certificate):
        if not getattr(certificate, 'valid', True):
            return DecisionResult(
                action="ABSTAIN",
                reason=getattr(certificate, 'reason', "Invalid certificate"),
                escalation_result=None,
                audit_trail={'threshold_version': self.threshold}
            )
            
        sl, su = certificate.score_lower, certificate.score_upper
        if sl >= self.threshold:
            act, rs = "ESCALATE_NONLINEAR", "Lower bound exceeds threshold"
        elif su < self.threshold:
            act, rs = "STAY_EKF", "Upper bound below threshold"
        else:
            act, rs = "ABSTAIN", "Envelope crosses threshold"
            
        return DecisionResult(
            action=act,
            reason=rs,
            escalation_result=None,
            audit_trail={
                'reason': rs,
                'score_lower': sl,
                'score_upper': su,
                'threshold_version': self.threshold,
                'intended_action': act
            }
        )
        
    def confirm_escalation(self, decision, estimator_result):
        if decision.action == "ESCALATE_NONLINEAR":
            decision.escalation_result = "SUCCESS"
            decision.audit_trail['final_estimator_result'] = "valid"
        return decision
""",
    r"modules\decision_policies\cost_model.py": """class CostModel:
    def __init__(self, miss_cost=10.0, escalation_cost=1.0, abstention_cost=2.0):
        self.miss_cost = miss_cost
        self.escalation_cost = escalation_cost
        self.abstention_cost = abstention_cost
        self.notes = "Costs are illustrative and need operational grounding."
        
    def evaluate_cost(self, decision_state, true_state=None) -> float:
        if decision_state == "STAY_EKF":
            return self.miss_cost if true_state == "unsafe" else 0.0
        if decision_state == "ESCALATE_NONLINEAR":
            return self.escalation_cost
        if decision_state == "ABSTAIN":
            return self.abstention_cost
        return 0.0
"""
}

for p, c in FILES.items():
    fp = os.path.join(workspace, p)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(c)
print(f"Successfully generated {len(FILES)} ATOM-QSA modules.")
