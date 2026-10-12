from __future__ import annotations

from typing import Any

from garminconnect.workout import (
    ConditionType,
    CyclingWorkout,
    ExecutableStep,
    RepeatGroup,
    RunningWorkout,
    SportType,
    StepType,
    TargetType,
    WorkoutSegment,
)

from .plan_schema import PlannedWorkout, Step, StepTarget

_STEP_TYPE_KEY = {
    "warmup": "warmup",
    "interval": "interval",
    "recovery": "recovery",
    "cooldown": "cooldown",
}
_STEP_TYPE_ID = {
    "warmup": StepType.WARMUP,
    "interval": StepType.INTERVAL,
    "recovery": StepType.RECOVERY,
    "cooldown": StepType.COOLDOWN,
}
_CONDITION = {
    "time": (ConditionType.TIME, "time"),
    "distance": (ConditionType.DISTANCE, "distance"),
}
_SPORT_TYPE = {
    "running": {"sportTypeId": SportType.RUNNING, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": SportType.CYCLING, "sportTypeKey": "cycling"},
}


def _pace_to_mps(pace_min_per_km: float) -> float:
    return 1000 / (pace_min_per_km * 60)


def _target_fields(target: StepTarget) -> dict[str, Any]:
    """Retorna os campos de alvo no NIVEL DO STEP (irmaos de targetType, nao aninhados nele).

    Confirmado contra conta Garmin real em 2026-07-24: targetValueOne/targetValueTwo/zoneNumber
    sao campos do proprio ExecutableStep, nao do dict targetType. Colocar esses valores dentro de
    targetType faz a Garmin aceitar o tipo do alvo mas descartar os valores (voltam null). Tambem
    confirmado: para hr_zone, a Garmin ignora targetValueOne/Two (deriva o bpm da zona configurada
    no perfil do usuario) — so zoneNumber importa.
    """
    if target.kind == "hr_range" and target.hr_min_bpm and target.hr_max_bpm:
        # Faixa de bpm personalizada: mesmo targetType de zona, mas sem zoneNumber. Confirmado
        # contra conta real em 2026-10-12 (a Garmin devolve os valores 140/155 intactos).
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": TargetType.HEART_RATE_ZONE,
            },
            "targetValueOne": target.hr_min_bpm,
            "targetValueTwo": target.hr_max_bpm,
        }

    if target.kind == "hr_zone" and target.hr_zone:
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.HEART_RATE_ZONE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": TargetType.HEART_RATE_ZONE,
            },
            "zoneNumber": target.hr_zone,
        }

    if target.kind == "pace" and target.pace_min_per_km:
        slow_pace = target.pace_min_per_km + target.pace_tolerance_min_per_km
        fast_pace = max(target.pace_min_per_km - target.pace_tolerance_min_per_km, 0.1)
        return {
            "targetType": {
                "workoutTargetTypeId": TargetType.PACE_ZONE,
                "workoutTargetTypeKey": "pace.zone",
                "displayOrder": TargetType.PACE_ZONE,
            },
            "targetValueOne": round(_pace_to_mps(slow_pace), 3),
            "targetValueTwo": round(_pace_to_mps(fast_pace), 3),
        }

    return {
        "targetType": {
            "workoutTargetTypeId": TargetType.NO_TARGET,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": TargetType.NO_TARGET,
        }
    }


def _build_executable(step: Step, order: int) -> ExecutableStep:
    type_id = _STEP_TYPE_ID[step.kind]
    cond_id, cond_key = _CONDITION[step.duration_type]
    return ExecutableStep(
        stepOrder=order,
        stepType={
            "stepTypeId": type_id,
            "stepTypeKey": _STEP_TYPE_KEY[step.kind],
            "displayOrder": type_id,
        },
        endCondition={
            "conditionTypeId": cond_id,
            "conditionTypeKey": cond_key,
            "displayOrder": cond_id,
            "displayable": True,
        },
        endConditionValue=step.duration_value,
        **_target_fields(step.target),
    )


def _build_steps(steps: list[Step], start_order: int) -> tuple[list[Any], int]:
    built: list[Any] = []
    order = start_order
    for step in steps:
        if step.repeat_iterations and step.repeat_steps:
            inner, order = _build_steps(step.repeat_steps, order)
            built.append(
                RepeatGroup(
                    stepOrder=order,
                    stepType={
                        "stepTypeId": StepType.REPEAT,
                        "stepTypeKey": "repeat",
                        "displayOrder": StepType.REPEAT,
                    },
                    numberOfIterations=step.repeat_iterations,
                    workoutSteps=inner,
                    endCondition={
                        "conditionTypeId": ConditionType.ITERATIONS,
                        "conditionTypeKey": "iterations",
                        "displayOrder": ConditionType.ITERATIONS,
                        "displayable": False,
                    },
                    endConditionValue=float(step.repeat_iterations),
                )
            )
            order += 1
        else:
            built.append(_build_executable(step, order))
            order += 1
    return built, order


def _flatten(steps: list[Step]) -> list[Step]:
    flat: list[Step] = []
    for step in steps:
        if step.repeat_iterations and step.repeat_steps:
            flat.extend(_flatten(step.repeat_steps) * step.repeat_iterations)
        else:
            flat.append(step)
    return flat


def build_workout(plan: PlannedWorkout) -> RunningWorkout | CyclingWorkout:
    steps, _ = _build_steps(plan.steps, start_order=1)
    total_seconds = sum(
        s.duration_value for s in _flatten(plan.steps) if s.duration_type == "time"
    )

    segment = WorkoutSegment(
        segmentOrder=1,
        sportType=_SPORT_TYPE[plan.sport],
        workoutSteps=steps,
    )

    workout_cls = RunningWorkout if plan.sport == "running" else CyclingWorkout
    return workout_cls(
        workoutName=plan.name,
        estimatedDurationInSecs=int(total_seconds) or 1,
        workoutSegments=[segment],
        description=plan.description,
    )
