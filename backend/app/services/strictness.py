"""
Strictness Profiles and Exercise ROM Targets.

Defines the feedback strictness levels (lenient, moderate, strict, drill_sergeant)
and the minimum acceptable Range of Motion (ROM) for specific exercises.
"""

from dataclasses import dataclass
from enum import Enum


class StrictnessLevel(str, Enum):
    LENIENT = "lenient"
    MODERATE = "moderate"
    STRICT = "strict"
    DRILL_SERGEANT = "drill_sergeant"


@dataclass
class StrictnessProfile:
    level: StrictnessLevel
    min_stability_threshold: float
    rom_multiplier: float
    stability_weight: float
    rom_weight: float
    penalty_curve_exponent: float


# Presets
_PROFILES = {
    StrictnessLevel.LENIENT: StrictnessProfile(
        level=StrictnessLevel.LENIENT,
        min_stability_threshold=0.3,  # Very forgiving
        rom_multiplier=0.5,           # Only requires 50% of target ROM
        stability_weight=0.6,
        rom_weight=0.4,
        penalty_curve_exponent=1.0,   # Linear, soft penalties
    ),
    StrictnessLevel.MODERATE: StrictnessProfile(
        level=StrictnessLevel.MODERATE,
        min_stability_threshold=0.5,
        rom_multiplier=0.75,
        stability_weight=0.5,
        rom_weight=0.5,
        penalty_curve_exponent=1.2,
    ),
    StrictnessLevel.STRICT: StrictnessProfile(
        level=StrictnessLevel.STRICT,
        min_stability_threshold=0.65,
        rom_multiplier=1.0,           # Requires 100% of target ROM
        stability_weight=0.4,
        rom_weight=0.6,
        penalty_curve_exponent=1.5,   # Steeper penalties
    ),
    StrictnessLevel.DRILL_SERGEANT: StrictnessProfile(
        level=StrictnessLevel.DRILL_SERGEANT,
        min_stability_threshold=0.8,
        rom_multiplier=1.2,           # Requires 120% of target ROM (hyper-strict)
        stability_weight=0.3,
        rom_weight=0.7,
        penalty_curve_exponent=2.0,   # Brutal penalties for low scores
    ),
}

# Base target ROM (in degrees) per joint for various exercises.
# Note: Isometrics like "plank" expect ~0 degrees of ROM.
# Joint names match _ANGLE_JOINT_NAMES in analysis.py
_EXERCISE_ROM_TARGETS = {
    "squat": {
        "Right Knee": 90.0,
        "Left Knee": 90.0,
        "Right Hip": 80.0,
        "Left Hip": 80.0,
    },
    "deadlift": {
        "Right Hip": 90.0,
        "Left Hip": 90.0,
        "Right Knee": 30.0,
        "Left Knee": 30.0,
    },
    "barbell_biceps_curl": {
        "Right Elbow": 100.0,
        "Left Elbow": 100.0,
    },
    "overhead_press": {
        "Right Shoulder": 80.0,
        "Left Shoulder": 80.0,
        "Right Elbow": 90.0,
        "Left Elbow": 90.0,
    },
    "lunge": {
        "Right Knee": 70.0,
        "Left Knee": 70.0,
        "Right Hip": 60.0,
        "Left Hip": 60.0,
    },
    "push_up": {
        "Right Elbow": 70.0,
        "Left Elbow": 70.0,
        "Right Shoulder": 60.0,
        "Left Shoulder": 60.0,
    },
    "plank": {
        # Isometric - expects minimal ROM
        "Right Knee": 0.0,
        "Left Knee": 0.0,
        "Right Hip": 0.0,
        "Left Hip": 0.0,
        "Right Shoulder": 0.0,
        "Left Shoulder": 0.0,
    }
}


def get_profile(level: str | StrictnessLevel) -> StrictnessProfile:
    """Get the strictness profile, defaulting to MODERATE if invalid."""
    try:
        if isinstance(level, str):
            level = StrictnessLevel(level.lower())
        return _PROFILES[level]
    except ValueError:
        return _PROFILES[StrictnessLevel.MODERATE]


def get_rom_target(exercise_slug: str, joint_name: str, profile: StrictnessProfile) -> float:
    """
    Get the ROM target (in degrees) for a joint in a specific exercise,
    scaled by the strictness profile.
    Returns 0.0 if the joint is not considered a primary mover for the exercise.
    """
    targets = _EXERCISE_ROM_TARGETS.get(exercise_slug, {})
    
    # If the joint isn't tracked for ROM in this exercise, target is 0
    base_target = targets.get(joint_name, 0.0)
    
    # Isometrics get 0 target
    if base_target <= 0.0:
        return 0.0
        
    return base_target * profile.rom_multiplier
