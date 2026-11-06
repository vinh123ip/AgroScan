"""Pure-Python ISO/IEC 18004 QR Code matrix encoder (Versions 1–4, Byte mode).

Generates standard, smartphone- and 2D-imager-scannable QR codes for AgroScan
box labels (``AGS:<ORDER>-<BOX>/<TOTAL>``) with zero external dependencies.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GF(256) arithmetic (primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 = 0x11D)
# ---------------------------------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256


def _init_gf() -> None:
    value = 1
    for i in range(255):
        _EXP[i] = value
        _LOG[value] = i
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def rs_encode(data: list[int], ec_count: int) -> list[int]:
    """Compute ``ec_count`` Reed-Solomon error-correction codewords for ``data``."""
    gen = [1]
    for i in range(ec_count):
        nxt = [0] * (len(gen) + 1)
        for j, coeff in enumerate(gen):
            nxt[j] ^= coeff
            nxt[j + 1] ^= _gf_mul(coeff, _EXP[i])
        gen = nxt

    rem = [0] * ec_count
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        if factor:
            for j in range(ec_count):
                rem[j] ^= _gf_mul(gen[j + 1], factor)
    return rem


def rs_syndromes(codewords: list[int], ec_count: int) -> list[int]:
    """Evaluate codeword polynomial at alpha^0 .. alpha^(ec_count-1) (all 0 when valid)."""
    out: list[int] = []
    for i in range(ec_count):
        root = _EXP[i]
        acc = 0
        for cw in codewords:
            acc = _gf_mul(acc, root) ^ cw
        out.append(acc)
    return out


# ---------------------------------------------------------------------------
# Single-block version parameters: (version, ecc_format_bits, data_codewords, ec_codewords)
# ECC format bits per ISO/IEC 18004 Table 25: M = 0b00, L = 0b01
# ---------------------------------------------------------------------------

_SINGLE_BLOCK_SPECS: tuple[tuple[int, int, int, int], ...] = (
    (1, 0b00, 16, 10),  # Version 1-M (21x21): up to 14 UTF-8 bytes
    (2, 0b00, 28, 16),  # Version 2-M (25x25): up to 26 UTF-8 bytes
    (3, 0b00, 44, 26),  # Version 3-M (29x29): up to 42 UTF-8 bytes
    (4, 0b01, 80, 20),  # Version 4-L (33x33): up to 78 UTF-8 bytes
)

MAX_QR_BYTES = 78


def format_bits(ecc_bits: int, mask_id: int) -> int:
    """Compute the 15-bit BCH(15, 5) format word masked with 0x5412."""
    data = ((ecc_bits & 0b11) << 3) | (mask_id & 0b111)
    rem = data << 10
    for bit in range(14, 9, -1):
        if rem & (1 << bit):
            rem ^= 0x537 << (bit - 10)
    return ((data << 10) | rem) ^ 0x5412


def _mask_bit(mask_id: int, r: int, c: int) -> bool:
    if mask_id == 0:
        return (r + c) % 2 == 0
    if mask_id == 1:
        return r % 2 == 0
    if mask_id == 2:
        return c % 3 == 0
    if mask_id == 3:
        return (r + c) % 3 == 0
    if mask_id == 4:
        return ((r // 2) + (c // 3)) % 2 == 0
    if mask_id == 5:
        return ((r * c) % 2) + ((r * c) % 3) == 0
    if mask_id == 6:
        return (((r * c) % 2) + ((r * c) % 3)) % 2 == 0
    return (((r + c) % 2) + ((r * c) % 3)) % 2 == 0


def _encode_byte_segment(payload: bytes, data_codewords: int) -> list[int]:
    bits: list[int] = []

    def push(val: int, length: int) -> None:
        for shift in range(length - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push(0b0100, 4)          # Byte mode indicator
    push(len(payload), 8)    # 8-bit count for Versions 1–9
    for b in payload:
        push(b, 8)

    capacity_bits = data_codewords * 8
    terminator = min(4, capacity_bits - len(bits))
    bits.extend([0] * terminator)
    while len(bits) % 8 != 0:
        bits.append(0)

    codewords = [
        sum(bits[i + k] << (7 - k) for k in range(8))
        for i in range(0, len(bits), 8)
    ]
    pad_bytes = (0xEC, 0x11)
    idx = 0
    while len(codewords) < data_codewords:
        codewords.append(pad_bytes[idx % 2])
        idx += 1
    return codewords


def _build_base_grid(version: int) -> tuple[list[list[bool]], list[list[bool]]]:
    size = 17 + 4 * version
    modules = [[False] * size for _ in range(size)]
    is_func = [[False] * size for _ in range(size)]

    def set_func(r: int, c: int, dark: bool) -> None:
        if 0 <= r < size and 0 <= c < size:
            modules[r][c] = dark
            is_func[r][c] = True

    # Finder patterns + 1-module white separators
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                in_box = 0 <= dr <= 6 and 0 <= dc <= 6
                dark = in_box and (
                    dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)
                )
                set_func(top + dr, left + dc, dark)

    # Alignment pattern for Versions 2–4 centered at (size - 7, size - 7)
    if version >= 2:
        center = size - 7
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                dist = max(abs(dr), abs(dc))
                set_func(center + dr, center + dc, dist in (0, 2))

    # Timing patterns
    for i in range(8, size - 8):
        if not is_func[6][i]:
            set_func(6, i, i % 2 == 0)
        if not is_func[i][6]:
            set_func(i, 6, i % 2 == 0)

    # Dark module & reserved format areas
    set_func(size - 8, 8, True)
    for i in range(9):
        if not is_func[8][i]:
            set_func(8, i, False)
        if not is_func[i][8]:
            set_func(i, 8, False)
    for i in range(8):
        set_func(8, size - 1 - i, False)
    for i in range(7):
        set_func(size - 1 - i, 8, False)

    return modules, is_func


def _write_format_bits(modules: list[list[bool]], ecc_bits: int, mask_id: int) -> None:
    size = len(modules)
    fmt = format_bits(ecc_bits, mask_id)

    tl_cols = (0, 1, 2, 3, 4, 5, 7, 8)
    for idx, col in enumerate(tl_cols):
        modules[8][col] = bool((fmt >> (14 - idx)) & 1)

    tl_rows = (7, 5, 4, 3, 2, 1, 0)
    for idx, row in enumerate(tl_rows):
        modules[row][8] = bool((fmt >> (6 - idx)) & 1)

    for idx in range(7):
        modules[size - 1 - idx][8] = bool((fmt >> (14 - idx)) & 1)
    for idx in range(8):
        modules[8][size - 8 + idx] = bool((fmt >> (7 - idx)) & 1)


def _zigzag_coords(size: int, is_func: list[list[bool]]) -> list[tuple[int, int]]:
    coords: list[tuple[int, int]] = []
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for dc in (0, 1):
                c = col - dc
                if not is_func[row][c]:
                    coords.append((row, c))
        upward = not upward
        col -= 2
    return coords


def _penalty_score(grid: list[list[bool]]) -> int:
    size = len(grid)
    score = 0

    # N1: runs of 5+ identical modules in rows and columns
    for line in list(grid) + [[grid[r][c] for r in range(size)] for c in range(size)]:
        run_val = line[0]
        run_len = 1
        for cell in line[1:]:
            if cell == run_val:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_val = cell
                run_len = 1
        if run_len >= 5:
            score += 3 + (run_len - 5)

    # N2: 2x2 blocks
    for r in range(size - 1):
        for c in range(size - 1):
            v = grid[r][c]
            if grid[r][c + 1] == v and grid[r + 1][c] == v and grid[r + 1][c + 1] == v:
                score += 3

    # N3: finder-like 1:1:3:1:1 patterns next to 4 light modules
    pat_a = [True, False, True, True, True, False, True, False, False, False, False]
    pat_b = [False, False, False, False, True, False, True, True, True, False, True]
    for line in list(grid) + [[grid[r][c] for r in range(size)] for c in range(size)]:
        for idx in range(size - 10):
            window = line[idx:idx + 11]
            if window == pat_a or window == pat_b:
                score += 40

    # N4: dark module balance
    dark = sum(sum(1 for cell in row if cell) for row in grid)
    total = size * size
    deviation = abs(dark * 20 - total * 10) // total
    score += deviation * 10
    return score


def encode_qr_matrix(text: str) -> list[list[bool]]:
    """Encode ``text`` into a square boolean matrix (``True`` = dark module).

    Raises:
        ValueError: If ``text`` is empty or exceeds ``MAX_QR_BYTES`` UTF-8 bytes.
    """
    payload = text.encode("utf-8")
    if not payload:
        raise ValueError("QR payload cannot be empty.")
    if len(payload) > MAX_QR_BYTES:
        raise ValueError(f"QR payload exceeds {MAX_QR_BYTES} bytes ({len(payload)} bytes).")

    spec = next(
        s for s in _SINGLE_BLOCK_SPECS if len(payload) + 2 <= s[2]
    )
    version, ecc_bits, data_cw, ec_cw = spec

    data_bytes = _encode_byte_segment(payload, data_cw)
    all_codewords = data_bytes + rs_encode(data_bytes, ec_cw)
    bit_stream = [
        bool((cw >> shift) & 1)
        for cw in all_codewords
        for shift in range(7, -1, -1)
    ]

    base_modules, is_func = _build_base_grid(version)
    coords = _zigzag_coords(len(base_modules), is_func)
    for idx, (r, c) in enumerate(coords):
        base_modules[r][c] = bit_stream[idx] if idx < len(bit_stream) else False

    best_grid: list[list[bool]] | None = None
    best_score: int | None = None
    size = len(base_modules)
    for mask_id in range(8):
        candidate = [row[:] for row in base_modules]
        for r in range(size):
            for c in range(size):
                if not is_func[r][c] and _mask_bit(mask_id, r, c):
                    candidate[r][c] = not candidate[r][c]
        _write_format_bits(candidate, ecc_bits, mask_id)
        score = _penalty_score(candidate)
        if best_score is None or score < best_score:
            best_score = score
            best_grid = candidate

    assert best_grid is not None
    return best_grid
