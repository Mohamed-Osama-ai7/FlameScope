"""Method-card contract: no calculation is exposed without formula, source, units and limits."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.regimes import CombustionRegime


class VariableSpec(BaseModel):
    symbol: str
    name: str
    unit: str
    role: str = Field(pattern="^(input|output|parameter)$")


class Reference(BaseModel):
    citation: str
    doi: str | None = None


class MethodCard(BaseModel):
    method_id: str
    version: str
    title: str
    regimes: list[CombustionRegime]
    formula: str
    variables: list[VariableSpec]
    references: list[Reference] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    validity_limits: list[str] = Field(min_length=1)
    required_inputs: list[str] = Field(min_length=1)
    uncertainty_method: str
    validation: list[str] = Field(min_length=1)
    abstention_conditions: list[str] = Field(min_length=1)
    status: str = Field(
        description="'implemented_unvalidated_on_nasa_data' until checked against a real FLEX run"
    )


D2_LAW_CARD = MethodCard(
    method_id="droplet.d2_law_burning_rate_constant",
    version="0.1.0",
    title="Quasi-steady burning-rate constant from droplet diameter history (d^2-law)",
    regimes=[CombustionRegime.FLEX_DROPLET],
    formula="D(t)^2 = D0^2 - K * t ;  K = -d(D^2)/dt estimated by (weighted) least squares",
    variables=[
        VariableSpec(symbol="t", name="time since window start", unit="s", role="input"),
        VariableSpec(symbol="D", name="droplet diameter", unit="mm", role="input"),
        VariableSpec(symbol="sigma_D", name="diameter 1-sigma uncertainty", unit="mm", role="input"),
        VariableSpec(
            symbol="K",
            name="burning_rate_constant_d2_fit_mm2_s (calculated; distinct from reported K)",
            unit="mm^2/s",
            role="output",
        ),
        VariableSpec(symbol="D0^2", name="fitted intercept", unit="mm^2", role="output"),
    ],
    references=[
        Reference(
            citation=(
                "Godsave, G.A.E. (1953). Studies of the combustion of drops in a fuel spray - "
                "the burning of single drops of fuel. Proc. Combust. Inst. 4, 818-830."
            ),
            doi="10.1016/S0082-0784(53)80107-4",  # verified via Crossref 2026-11-13
        ),
        Reference(
            citation=(
                "Law, C.K. (1982). Recent advances in droplet vaporization and combustion. "
                "Prog. Energy Combust. Sci. 8, 171-201."
            ),
            doi="10.1016/0360-1285(82)90011-9",  # verified via Crossref 2026-11-13
        ),
    ],
    assumptions=[
        "Spherically symmetric, quasi-steady gas phase (approached in microgravity).",
        "Constant properties and ambient conditions over the analysed window.",
        "Single-component fuel; no significant water absorption or composition change in window.",
    ],
    validity_limits=[
        "Exclude ignition/heat-up transient and near-extinction data; the caller selects the window.",
        "FLEX droplets show radiative extinction and cool-flame burning (e.g. n-alkanes); "
        "D^2(t) may be non-linear there and a single K is then not meaningful.",
        "Not applicable to solid fuels (BASS-II, Saffire).",
    ],
    required_inputs=[
        "regime = flex_droplet (isolated liquid-fuel droplet); other regimes rejected",
        "fuel name as given in the source",
        "time in s and diameter in mm (declared units; no implicit conversion)",
        "At least 3 (t, D) samples from one droplet run within a declared quasi-steady window",
        "window_selection: how the quasi-steady window was chosen (tool does not choose it)",
        "Source provenance: source_id, locator (file/page/table/frame), extraction method; "
        "the source must be ACQUIRED/VERIFIED in the registry or unregistered (flagged)",
    ],
    uncertainty_method=(
        "Weighted least squares with sigma(D^2) = 2 D sigma_D when sigma_D is supplied, otherwise "
        "ordinary least squares with residual-based covariance. 95% CI from Student t with n-2 dof "
        "(quantile from app/science/stats.py, tested against t-table values). "
        "Frames are serially correlated, so this CI is a lower bound; replicate runs are the "
        "independent unit."
    ),
    validation=[
        "Unit tests recover K exactly from analytic D^2 = D0^2 - K t series.",
        "Not validated on NASA data. PSI-69 / NASA/TP-2015-216046 Table IX gives only reported "
        "per-test K (FLEX team's own fit, 'shortly after ignition to extinction'), no D(t); it "
        "cannot validate this implementation. Validation needs the report's per-test D(t) text "
        "files (DVD addendum / electronic data), not acquired.",
    ],
    abstention_conditions=[
        "Fewer than 3 samples, non-increasing time, or non-positive diameter",
        "Fitted K <= 0 (diameter not decreasing) - returned as not computable",
    ],
    status="implemented_unvalidated_on_nasa_data",
)

_TP_REF = Reference(
    citation=(
        "Dietrich, D.L. et al. (2015). Detailed Results from the Flame Extinguishment Experiment (FLEX) "
        "March 2009 to December 2011. NASA/TP-2015-216046, NTRS 20150023456 (column definitions, App. A.1; "
        "cited for semantics only, source not registered)."
    )
)

D2_CONSISTENCY_CARD = MethodCard(
    method_id="flex.d2_consistency_of_reported_values",
    version="0.1.0",
    title="Internal consistency of reported D0, Dext, K and burn time with the d^2-law (diagnostic)",
    regimes=[CombustionRegime.FLEX_DROPLET],
    formula="t_d2 = (D0^2 - Dext^2) / K ;  r = t_d2 / t_burn   (from D(t)^2 = D0^2 - K t)",
    variables=[
        VariableSpec(symbol="D0", name="initial droplet diameter (reported)", unit="mm", role="input"),
        VariableSpec(
            symbol="Dext", name="visible flame extinction diameter (reported)", unit="mm", role="input"
        ),
        VariableSpec(
            symbol="K", name="burning-rate constant (reported by the FLEX team)", unit="mm^2/s", role="input"
        ),
        VariableSpec(symbol="t_burn", name="burn time (reported)", unit="s", role="input"),
        VariableSpec(symbol="r", name="d^2-implied duration / reported burn time", unit="1", role="output"),
    ],
    references=[*D2_LAW_CARD.references, _TP_REF],
    assumptions=[
        "d^2-law with one constant K between D0 and Dext.",
        "Reported values are as tabulated in PSI-69; no value is corrected.",
    ],
    validity_limits=[
        "Only runs that end in Extinction with usable, unflagged D0, Dext, K and burn time, D0 > Dext > 0.",
        "K excludes the heat-up transient and the burn-time definition is undocumented, "
        "so r = 1 is not expected.",
    ],
    required_inputs=["PSI-69 run-level table via the verified loader"],
    uncertainty_method=(
        "Per run: worst-case interval from each value's reporting resolution (half a unit of the last "
        "written decimal), optionally widened by a caller-supplied diameter bound. Per fuel: median with "
        "percentile bootstrap 95% CI (9999 resamples, fixed seed). Review flag: Tukey fences, only when the "
        "whole interval lies outside them."
    ),
    validation=[
        "Unit tests: analytic examples for t_d2 and the interval bounds; deterministic bootstrap.",
        "Not a validation of the d^2-law or of NASA data: it screens reported values for internal "
        "consistency.",
    ],
    abstention_conditions=[
        "Run excluded with a counted reason when any input is missing, flagged or non-physical"
    ],
    status="implemented_diagnostic",
)

OXYGEN_EFFECT_CARD = MethodCard(
    method_id="flex.oxygen_effect_on_reported_k",
    version="0.1.0",
    title="Within-stratum linear association of ambient O2 mole fraction with reported K",
    regimes=[CombustionRegime.FLEX_DROPLET],
    formula="K = b0 + b1 * X_O2  (sensitivity: + b2 * D0); OLS with HC3 standard errors",
    variables=[
        VariableSpec(symbol="X_O2", name="ambient O2 mole fraction (reported)", unit="1", role="input"),
        VariableSpec(symbol="K", name="burning-rate constant (reported)", unit="mm^2/s", role="input"),
        VariableSpec(symbol="b1", name="slope", unit="mm^2/s per unit mole fraction", role="output"),
    ],
    references=[_TP_REF],
    assumptions=[
        "Within a stratum (fuel, N2-only diluent, pressure cluster, support mode) O2 is the varied "
        "condition.",
        "Linear over the observed O2 range.",
    ],
    validity_limits=[
        "Association, not causation; no extrapolation beyond the observed O2 range.",
        "Support mode is from unregistered NASA/TP captions and is used only as a stratifier.",
    ],
    required_inputs=["PSI-69 run-level table via the verified loader"],
    uncertainty_method=(
        "HC3 heteroskedasticity-robust standard errors; 95% CI from Student t on the residual dof "
        "(statsmodels, use_t=True)."
    ),
    validation=["Unit tests recover exact coefficients from noiseless synthetic data."],
    abstention_conditions=["Stratum with n < 8 or fewer than 3 distinct O2 levels: not computed"],
    status="implemented_descriptive",
)

METHOD_REGISTRY: dict[str, MethodCard] = {
    c.method_id: c for c in (D2_LAW_CARD, D2_CONSISTENCY_CARD, OXYGEN_EFFECT_CARD)
}
