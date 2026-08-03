from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepKind = Literal["warmup", "interval", "recovery", "cooldown"]
DurationType = Literal["time", "distance"]
TargetKind = Literal["none", "hr_zone", "pace"]


class StepTarget(BaseModel):
    kind: TargetKind = "none"
    hr_zone: int | None = Field(default=None, description="1 a 5, usado quando kind=hr_zone")
    pace_min_per_km: float | None = Field(default=None, description="Pace alvo central, usado quando kind=pace")
    pace_tolerance_min_per_km: float = Field(default=0.15, description="Faixa +/- ao redor do pace alvo")


class Step(BaseModel):
    kind: StepKind
    duration_type: DurationType
    duration_value: float = Field(description="Segundos se duration_type=time, metros se duration_type=distance")
    target: StepTarget = Field(default_factory=StepTarget)
    repeat_iterations: int | None = Field(default=None, description="Se definido, este step e repetido N vezes")
    repeat_steps: list["Step"] | None = Field(default=None, description="Steps internos do bloco de repeticao")


class PlannedWorkout(BaseModel):
    date: str = Field(description="Data alvo do treino, formato YYYY-MM-DD")
    sport: Literal["running", "cycling"]
    name: str
    description: str
    steps: list[Step]


class CoachResponse(BaseModel):
    analysis: str = Field(description="Analise em portugues do desempenho recente e racional do proximo bloco de treinos")
    highlights: str = Field(description="O que melhorou desde o ciclo anterior (consistencia, FC, pace, volume, etc). Se nao houver historico suficiente para comparar, diga isso explicitamente.")
    improvement_areas: str = Field(description="Pontos de atencao e o que pode melhorar (ex: FC muito alta em rodagens leves, falta de consistencia, risco de overtraining)")
    next_targets: str = Field(description="Metricas e alvos concretos para os proximos treinos: zonas de FC, paces alvo, volume semanal esperado")
    recovery_assessment: str = Field(description="Avaliacao de sono, estresse e HRV recentes, e como isso concretamente mudou (ou nao) as decisoes do bloco de treinos gerado")
    planned_workouts: list[PlannedWorkout]
