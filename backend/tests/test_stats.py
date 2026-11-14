"""Student-t quantile vs standard two-sided 95% t-table values (t_0.975)."""
import pytest

from app.science.stats import student_t_cdf, student_t_ppf


@pytest.mark.parametrize(
    "dof,expected",
    [(1, 12.7062047), (2, 4.3026527), (5, 2.5705818), (10, 2.2281389), (30, 2.0422725)],
)
def test_t_975_matches_table(dof, expected):
    assert student_t_ppf(0.975, dof) == pytest.approx(expected, rel=1e-6)


def test_symmetry_and_cdf_roundtrip():
    assert student_t_ppf(0.025, 7) == pytest.approx(-student_t_ppf(0.975, 7))
    assert student_t_cdf(student_t_ppf(0.9, 4), 4) == pytest.approx(0.9, abs=1e-10)
    assert student_t_cdf(0.0, 3) == pytest.approx(0.5)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        student_t_ppf(1.0, 3)
    with pytest.raises(ValueError):
        student_t_cdf(1.0, 0)
