"""E2 curve parameters — aligned with platform §2.1 / Client.py semantics."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ecdsa.ellipticcurve import CurveFp, Point


@dataclass(frozen=True)
class CurveE2Info:
    curve_base_field: int
    a: int
    b: int
    curve_order: int
    generator_x: int
    generator_y: int


@dataclass
class KeyMaterial:
    curve: CurveFp
    curve_base_field: int
    curve_order: int
    generator: Point
    public_key: Point
    private_scalar: int


def curve_e2_info() -> tuple[CurveFp, int, int, Point, Point]:
    info = CurveE2Info(
        curve_base_field=7237005577332262213973186563042994240857116359379907606001950938285454250989,
        a=3491403595575449084947959021303599933011749826127899762162894550148391771037,
        b=3633908682298454119909199192149978293706667958442512986315258451820769071958,
        generator_x=4561981307020378385254256586024830594940985765081274686120783167106442831732,
        generator_y=684120277165286233470758410892647831027470652988879249692043589061244861334,
        curve_order=7237005577332262213973186563042994240704759454384003648147593987722918659549,
    )
    curve = CurveFp(info.curve_base_field, info.a, info.b)
    generator = Point(curve, info.generator_x, info.generator_y)
    identity = generator * 0
    return curve, info.curve_base_field, info.curve_order, generator, identity


def key_gen() -> KeyMaterial:
    curve, base_field, order, generator, _ = curve_e2_info()
    x = random.randrange(1, order - 1)
    h = x * generator
    return KeyMaterial(
        curve=curve,
        curve_base_field=base_field,
        curve_order=order,
        generator=generator,
        public_key=h,
        private_scalar=x,
    )
