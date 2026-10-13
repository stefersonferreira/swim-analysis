from pydantic import BaseModel, Field


class PoolProfile(BaseModel):
    """Geometria da piscina. Coordenadas da piscina em metros:
    x ao longo do comprimento, a partir da parede de saída (0..length_m);
    y através das raias, a partir da corda 0 (borda de um lado) até lanes * lane_width_m.
    """

    schema_version: int = 1
    name: str = "Piscina 25 m"
    length_m: float = 25.0
    lanes: int = 8
    lane_width_m: float = 2.5
    marks_m: list[float] = Field(
        default_factory=lambda: [5.0, 10.0, 15.0, 20.0],
        description="Posições x (a partir da parede de saída) com marcas visíveis "
        "(bandeirolas a 5 m, troca de cor das boias a 15 m de cada parede)",
    )

    @property
    def width_m(self) -> float:
        return self.lanes * self.lane_width_m

    def rope_y(self, rope_index: int) -> float:
        if not 0 <= rope_index <= self.lanes:
            raise ValueError(f"corda {rope_index} fora de 0..{self.lanes}")
        return rope_index * self.lane_width_m

    def lane_center_y(self, lane: int) -> float:
        """Centro da raia `lane` (1..lanes), raia 1 entre as cordas 0 e 1."""
        return (lane - 0.5) * self.lane_width_m


class ClickPoint(BaseModel):
    image_xy: tuple[float, float]
    pool_xy: tuple[float, float]
    label: str | None = None


class Anchor(BaseModel):
    frame: int
    points: list[ClickPoint] = Field(default_factory=list)


class AnchorResult(BaseModel):
    frame: int
    homography: list[list[float]] | None = Field(
        None, description="3x3, imagem (pixels do proxy) -> piscina (m)"
    )
    mean_error_m: float | None = None
    max_error_m: float | None = None
    point_errors_m: list[float] = Field(default_factory=list)
    inliers: list[bool] = Field(default_factory=list)
    accepted: bool = False
    message: str | None = None


class Calibration(BaseModel):
    schema_version: int = 1
    pool: PoolProfile = Field(default_factory=PoolProfile)
    anchors: list[Anchor] = Field(default_factory=list)
    results: list[AnchorResult] = Field(default_factory=list)
