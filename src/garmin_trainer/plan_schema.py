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


Readiness = Literal["alta", "moderada", "baixa"]
EffortRating = Literal["leve", "moderado", "forte", "muito forte"]


class ActivityAnalysis(BaseModel):
    headline: str = Field(description="Uma frase com o veredito do treino, citando o numero mais importante")
    effort_rating: EffortRating = Field(description="Esforco real percebido pelos dados (FC, zonas, training effect)")
    execution_vs_plan: str = Field(description="Comparacao com o treino prescrito pelo Greg (pace/FC alvo x executado, por bloco). Se nao houve treino prescrito, compare com o proposito aparente da atividade e com as zonas do perfil")
    heart_rate_analysis: str = Field(description="FC media/max, tempo por zona, desacoplamento pace:FC/deriva cardiaca, efeito do calor se relevante")
    pacing_analysis: str = Field(description="Distribuicao do ritmo nas voltas (saiu rapido demais? manteve? negativou?), cadencia")
    highlights: str = Field(description="O que foi positivo ou evoluiu em relacao ao historico")
    attention_points: str = Field(description="Pontos de atencao concretos")
    recovery_tips: str = Field(description="Orientacoes de recuperacao para as proximas horas (hidratacao, sono, alimentacao) - sem prescrever treinos")


class MorningReport(BaseModel):
    headline: str = Field(description="Uma frase resumindo como o atleta acordou hoje")
    readiness: Readiness = Field(description="Prontidao do dia, considerando sono, HRV, FC de repouso e body battery")
    sleep_analysis: str = Field(description="Sono da noite passada: duracao, score, fases (profundo/REM), estresse e FC no sono, comparado aos ultimos dias")
    recovery_analysis: str = Field(description="HRV (noite x media 7d x faixa normal), FC de repouso x media 7d, body battery ao acordar")
    yesterday_analysis: str = Field(description="Como foi o dia de ontem: estresse (medio e minutos em estresse alto), passos x meta, minutos de intensidade, treinos feitos e carga")
    trends: str = Field(description="Tendencias dos ultimos 7 dias que merecem atencao (para melhor ou pior), com numeros")
    goals: str = Field(description="Leitura em relacao aos objetivos do perfil: prova alvo (dias que faltam, previsao de tempo do Garmin) e peso")
    tips_for_today: str = Field(description="2 a 4 dicas praticas para hoje (sono, estresse, hidratacao, intensidade a respeitar no treino do Greg se houver) - sem prescrever treinos")


class TrainerReview(BaseModel):
    summary: str = Field(description="Resumo geral em portugues da analise das ultimas atividades")
    highlights: str = Field(description="O que evoluiu nesses treinos (pace, FC, controle de deriva cardiaca, consistencia)")
    improvement_areas: str = Field(description="Pontos de atencao e o que precisa melhorar")
    recovery_assessment: str = Field(description="Leitura de sono/estresse/HRV/peso no periodo e como isso se relaciona com os treinos")


class CoachResponse(BaseModel):
    analysis: str = Field(description="Analise em portugues do desempenho recente e racional do proximo bloco de treinos")
    highlights: str = Field(description="O que melhorou desde o ciclo anterior (consistencia, FC, pace, volume, etc). Se nao houver historico suficiente para comparar, diga isso explicitamente.")
    improvement_areas: str = Field(description="Pontos de atencao e o que pode melhorar (ex: FC muito alta em rodagens leves, falta de consistencia, risco de overtraining)")
    next_targets: str = Field(description="Metricas e alvos concretos para os proximos treinos: zonas de FC, paces alvo, volume semanal esperado")
    recovery_assessment: str = Field(description="Avaliacao de sono, estresse e HRV recentes, e como isso concretamente mudou (ou nao) as decisoes do bloco de treinos gerado")
    planned_workouts: list[PlannedWorkout]
