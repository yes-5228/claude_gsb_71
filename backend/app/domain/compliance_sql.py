"""SQL expressions for the shared compliance-rate caliber."""
from sqlalchemy import and_, cast, func

from ..extensions import db
from ..models.measurement import Measurement
from .compliance import IGNORED_EXCEEDANCE_STATUS


def applicable_expression(measurement=Measurement):
    """Records with a stored standard limit can participate in compliance rates."""
    return measurement.limit_value.isnot(None)


def invalid_exceedance_expression(measurement=Measurement):
    """Auto-detected exceedance manually marked invalid through its exceedance row."""
    return and_(
        measurement.is_exceeded.is_(True),
        measurement.exceedance.has(status=IGNORED_EXCEEDANCE_STATUS),
    )


def evaluated_expression(measurement=Measurement):
    """Finite-valued records that are not marked invalid."""
    return and_(applicable_expression(measurement), ~invalid_exceedance_expression(measurement))


def valid_exceeded_expression(measurement=Measurement):
    return and_(measurement.is_exceeded.is_(True), evaluated_expression(measurement))


def integer_sum(expression, label=None):
    """Boolean aggregate that is always returned as an int."""
    aggregate = func.sum(cast(expression, db.Integer))
    return aggregate.label(label) if label else aggregate
