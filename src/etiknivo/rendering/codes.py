"""QR codes and Code 128 barcodes, written for Etiknivo's small labels.

Both encoders follow the public standards (ISO/IEC 18004 for QR, ISO/IEC
15417 for Code 128) and return plain module patterns; the render engine turns
them into whole printer dots.

QR codes use byte mode (UTF-8) in versions 1 to 6 with error correction level
M, or L when M does not fit.  A 12 mm label has room for about 88 dots, so a
larger version would need modules under two dots, too small to scan.
"""

from __future__ import annotations

from collections.abc import Iterator

# -- Reed-Solomon over GF(256), polynomial 0x11D -------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    """Coefficients of (x - a^0)(x - a^1)...(x - a^(degree-1)), highest first."""
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            nxt[j] ^= c
            nxt[j + 1] ^= _gf_mul(c, _EXP[i])
        poly = nxt
    return poly


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    gen = _rs_generator(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for j in range(degree):
            rem[j] ^= _gf_mul(gen[j + 1], factor)
    return rem


# -- QR code tables (versions 1-6) ---------------------------------------------------

#: level -> version -> (EC codewords per block, number of blocks, data codewords per block)
_QR_BLOCKS = {
    "L": {1: (7, 1, 19), 2: (10, 1, 34), 3: (15, 1, 55), 4: (20, 1, 80), 5: (26, 1, 108),
          6: (18, 2, 68)},
    "M": {1: (10, 1, 16), 2: (16, 1, 28), 3: (26, 1, 44), 4: (18, 2, 32), 5: (24, 2, 43),
          6: (16, 4, 27)},
}
_QR_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_QR_LEVEL_BITS = {"L": 1, "M": 0}
QR_MAX_VERSION = 6


class CodeError(ValueError):
    """The text cannot be encoded (too long, unsupported characters)."""


def _qr_capacity(version: int, level: str) -> int:
    """Bytes that fit in byte mode."""
    _, blocks, per = _QR_BLOCKS[level][version]
    return (blocks * per * 8 - 4 - 8) // 8


def qr_capacity() -> int:
    return _qr_capacity(QR_MAX_VERSION, "L")


def _choose_qr(n: int) -> tuple[int, str]:
    for level in ("M", "L"):
        for version in range(1, QR_MAX_VERSION + 1):
            if n <= _qr_capacity(version, level):
                return version, level
    raise CodeError(f"{n} > {qr_capacity()}")


def _qr_codewords(data: bytes, version: int, level: str) -> list[int]:
    ec_len, blocks, per = _QR_BLOCKS[level][version]
    capacity = blocks * per * 8
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in reversed(range(length)))

    put(0b0100, 4)  # byte mode
    put(len(data), 8)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity - len(bits)))  # terminator
    put(0, -len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < blocks * per:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    data_blocks = [words[i * per:(i + 1) * per] for i in range(blocks)]
    ec_blocks = [_rs_remainder(b, ec_len) for b in data_blocks]
    out = [b[i] for i in range(per) for b in data_blocks]
    out += [b[i] for i in range(ec_len) for b in ec_blocks]
    return out


def _format_bits(level: str, mask: int) -> int:
    value = (_QR_LEVEL_BITS[level] << 3) | mask
    rem = value << 10
    for i in reversed(range(10, 15)):
        if rem & (1 << i):
            rem ^= 0x537 << (i - 10)
    return ((value << 10) | rem) ^ 0x5412


_MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


class _Matrix:
    def __init__(self, version: int) -> None:
        self.size = 17 + 4 * version
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]
        self._function_patterns(version)

    def set(self, r: int, c: int, dark: bool) -> None:
        self.dark[r][c] = dark
        self.fixed[r][c] = True

    def _finder(self, r0: int, c0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < self.size and 0 <= c < self.size:
                    ring = max(abs(dr - 3), abs(dc - 3))
                    self.set(r, c, ring in (0, 1, 3))

    def _function_patterns(self, version: int) -> None:
        n = self.size
        for i in range(n):  # timing patterns
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        self._finder(0, 0)
        self._finder(0, n - 7)
        self._finder(n - 7, 0)
        pos = _QR_ALIGN[version]
        for r in pos:
            for c in pos:
                if (r, c) in ((6, 6), (6, pos[-1]), (pos[-1], 6)):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        self.set(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
        self.place_format(0, 0)  # reserve the format areas
        self.set(n - 8, 8, True)  # the dark module

    def place_format(self, bits: int, _mask: int) -> None:
        n = self.size

        def bit(i: int) -> bool:
            return bool((bits >> i) & 1)

        for i in range(6):
            self.set(i, 8, bit(i))
        self.set(7, 8, bit(6))
        self.set(8, 8, bit(7))
        self.set(8, 7, bit(8))
        for i in range(9, 15):
            self.set(8, 14 - i, bit(i))
        for i in range(8):
            self.set(8, n - 1 - i, bit(i))
        for i in range(8, 15):
            self.set(n - 15 + i, 8, bit(i))
        self.set(n - 8, 8, True)

    def data_positions(self) -> Iterator[tuple[int, int]]:
        n = self.size
        right = n - 1
        upward = True
        while right >= 1:
            if right == 6:
                right = 5
            rows = range(n - 1, -1, -1) if upward else range(n)
            for r in rows:
                for c in (right, right - 1):
                    if not self.fixed[r][c]:
                        yield r, c
            upward = not upward
            right -= 2


def _penalty(m: list[list[bool]]) -> int:
    n = len(m)
    score = 0
    lines = m + [list(col) for col in zip(*m)]
    for line in lines:  # runs of five or more
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
    for r in range(n - 1):  # 2x2 blocks
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    pattern = [True, False, True, True, True, False, True]
    quiet = [False] * 4
    for line in lines:  # finder-like patterns
        for i in range(n - 6):
            if line[i:i + 7] == pattern:
                before = line[max(0, i - 4):i]
                after = line[i + 7:i + 11]
                if before == quiet[:len(before)] and len(before) == 4 \
                        or after == quiet[:len(after)] and len(after) == 4:
                    score += 40
    dark = sum(v for row in m for v in row)
    score += abs(dark * 20 - n * n * 10) // (n * n) * 10
    return score


def qr_matrix(text: str) -> list[list[bool]]:
    """The QR code for *text* as rows of modules (True = dark), without quiet zone."""
    data = text.encode("utf-8")
    version, level = _choose_qr(len(data))
    words = _qr_codewords(data, version, level)
    bits = [(w >> i) & 1 for w in words for i in reversed(range(8))]
    best: list[list[bool]] | None = None
    best_score = 0
    for mask, fn in enumerate(_MASKS):
        mx = _Matrix(version)
        for k, (r, c) in enumerate(mx.data_positions()):
            value = bool(bits[k]) if k < len(bits) else False
            mx.dark[r][c] = value ^ fn(r, c)
        mx.place_format(_format_bits(level, mask), mask)
        score = _penalty(mx.dark)
        if best is None or score < best_score:
            best, best_score = mx.dark, score
    assert best is not None
    return best


# -- Code 128 ------------------------------------------------------------------------

_C128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()
_START_B, _START_C, _CODE_B, _CODE_C, _STOP = 104, 105, 100, 99, 106


def code128_supported(ch: str) -> bool:
    return 32 <= ord(ch) <= 126


def _code128_values(text: str) -> list[int]:
    """Symbol values (start ... check) using sets B and C, switching to C for
    runs of digits where that saves space."""
    bad = sorted({ch for ch in text if not code128_supported(ch)})
    if bad:
        raise CodeError("".join(bad))
    if not text:
        raise CodeError("")

    def digits_at(i: int) -> int:
        n = 0
        while i + n < len(text) and text[i + n].isdigit():
            n += 1
        return n

    values: list[int] = []
    i = 0
    run = digits_at(0)
    use_c = run >= 4 and (run == len(text) or run % 2 == 0) or (run == len(text) and run == 2)
    values.append(_START_C if use_c else _START_B)
    current = "C" if use_c else "B"
    while i < len(text):
        run = digits_at(i)
        if current == "C":
            if run >= 2:
                values.append(int(text[i:i + 2]))
                i += 2
                continue
            values.append(_CODE_B)
            current = "B"
        end_run = i + run == len(text)
        if run >= 6 or (run >= 4 and end_run):
            if run % 2:  # odd run: one digit in B first
                values.append(ord(text[i]) - 32)
                i += 1
            values.append(_CODE_C)
            current = "C"
            continue
        values.append(ord(text[i]) - 32)
        i += 1
    check = values[0] + sum(v * k for k, v in enumerate(values[1:], start=1))
    values.append(check % 103)
    return values


def code128_modules(text: str) -> list[bool]:
    """Bars and spaces of *text* as modules (True = bar), without quiet zones."""
    out: list[bool] = []
    for v in _code128_values(text) + [_STOP]:
        bar = True
        for w in _C128[v]:
            out.extend([bar] * int(w))
            bar = not bar
    return out
