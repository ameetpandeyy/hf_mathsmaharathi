"""Enumerations for Maths Maharathi pipeline."""

from enum import Enum


class ExamType(str, Enum):
    """Supported examination categories."""
    SSC_CGL = "ssc_cgl"
    SSC_CHSL = "ssc_chsl"
    SBI_PO = "sbi_po"
    IBPS_PO = "ibps_po"
    IBPS_CLERK = "ibps_clerk"
    RRB_NTPC = "rrb_ntpc"
    RRB_GROUP_D = "rrb_group_d"


class SourceType(str, Enum):
    """Source provenance tracking for legal & copyright compliance.
    
    - 'pyq_reference': Extracted from genuine previous year questions. Used for
      pattern analysis, statistical modeling, and solver validation ONLY.
      NEVER exported to user-facing content packs unless rights_cleared is True.
    - 'original': Machine-generated or newly authored original question,
      solver-verified and human-approved. Fully eligible for content packs.
    """
    PYQ_REFERENCE = "pyq_reference"
    ORIGINAL = "original"


class DifficultyLevel(str, Enum):
    """Cognitive difficulty tier."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ReviewStatus(str, Enum):
    """Editorial and CRM review workflow states."""
    DRAFT = "draft"
    VERIFIED = "verified"
    APPROVED = "approved"
    REJECTED = "rejected"


class TopicSlug(str, Enum):
    """Standardized math curriculum topic slugs for Maths Maharathi."""
    SIMPLIFICATION = "simplification"
    NUMBER_SERIES = "number_series"
    PERCENTAGE = "percentage"
    RATIO_PROPORTION = "ratio_proportion"
    PROFIT_LOSS = "profit_loss"
    SIMPLE_COMPOUND_INTEREST = "simple_compound_interest"
    TIME_WORK = "time_work"
    SPEED_TIME_DISTANCE = "speed_time_distance"
    AVERAGES = "averages"
    MIXTURES_ALLIGATION = "mixtures_alligation"
    DATA_INTERPRETATION = "data_interpretation"
    ALGEBRA = "algebra"
    GEOMETRY = "geometry"
    MENSURATION = "mensuration"
    TRIGONOMETRY = "trigonometry"
    QUADRATIC_EQUATIONS = "quadratic_equations"
