"""
Self-contained, pure-Python QR Code generator for terminal display.
No external dependencies (no PIL, no qrcode package required).
Generates ANSI / Unicode text QR codes suitable for scanning directly from a terminal screen.
"""

import sys


class SimpleQRCode:
    """
    Minimal standalone QR Code generator (Version 1-4, Byte mode, EC Level L/M).
    Uses standard QR specifications (ISO/IEC 18004) with Reed-Solomon error correction.
    """

    # Galois Field GF(256) tables with primitive polynomial 0x11d
    GF_EXP = [0] * 512
    GF_LOG = [0] * 256

    _initialized = False

    @classmethod
    def _init_gf(cls):
        if cls._initialized:
            return
        x = 1
        for i in range(255):
            cls.GF_EXP[i] = x
            cls.GF_LOG[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11d
        for i in range(255, 512):
            cls.GF_EXP[i] = cls.GF_EXP[i - 255]
        cls._initialized = True

    @classmethod
    def _gf_mul(cls, x, y):
        if x == 0 or y == 0:
            return 0
        return cls.GF_EXP[cls.GF_LOG[x] + cls.GF_LOG[y]]

    @classmethod
    def _rs_poly(cls, num_ec):
        poly = [1]
        for i in range(num_ec):
            # multiply poly by (x - g^i)
            factor = [1, cls.GF_EXP[i]]
            new_p = [0] * (len(poly) + 1)
            for j, c in enumerate(poly):
                new_p[j] ^= cls._gf_mul(c, factor[0])
                new_p[j + 1] ^= cls._gf_mul(c, factor[1])
            poly = new_p
        return poly

    @classmethod
    def _rs_calc(cls, data_bytes, num_ec):
        cls._init_gf()
        poly = cls._rs_poly(num_ec)
        res = list(data_bytes) + [0] * num_ec
        for i in range(len(data_bytes)):
            lead = res[i]
            if lead != 0:
                for j in range(len(poly)):
                    res[i + j] ^= cls._gf_mul(poly[j], lead)
        return res[len(data_bytes):]

    @classmethod
    def generate_matrix(cls, text: str):
        """Generates a boolean 2D matrix representing QR modules (True=Black, False=White)."""
        cls._init_gf()
        data = text.encode("utf-8")
        
        # QR Version 3 (29x29) or Version 4 (33x33) handles typical URLs (up to 40-50 chars)
        if len(data) <= 17:
            ver = 1
            size = 21
            num_data = 19
            num_ec = 7
        elif len(data) <= 32:
            ver = 2
            size = 25
            num_data = 34
            num_ec = 10
        elif len(data) <= 53:
            ver = 3
            size = 29
            num_data = 55
            num_ec = 15
        else:
            ver = 4
            size = 33
            num_data = 78
            num_ec = 20

        # Encode mode: Byte (0100)
        bits = []
        def add_bits(val, count):
            for i in range(count - 1, -1, -1):
                bits.append((val >> i) & 1)

        add_bits(0b0100, 4)  # 8-bit byte mode
        add_bits(len(data), 8)  # Character count
        for b in data:
            add_bits(b, 8)

        # Terminator
        term_len = min(4, num_data * 8 - len(bits))
        add_bits(0, term_len)

        # Byte alignment
        while len(bits) % 8 != 0:
            bits.append(0)

        # Pad bytes
        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        while len(bits) < num_data * 8:
            add_bits(pad_bytes[pad_idx % 2], 8)
            pad_idx += 1

        # Convert to bytes
        data_bytes = []
        for i in range(0, len(bits), 8):
            byte_val = 0
            for b in bits[i:i+8]:
                byte_val = (byte_val << 1) | b
            data_bytes.append(byte_val)

        # Calculate error correction
        ec_bytes = cls._rs_calc(data_bytes, num_ec)
        full_codewords = data_bytes + ec_bytes

        # Create matrix
        matrix = [[None] * size for _ in range(size)]
        reserved = [[False] * size for _ in range(size)]

        def set_func(r, c, val):
            matrix[r][c] = val
            reserved[r][c] = True

        # Position patterns (Finders)
        def add_finder(start_r, start_c):
            for r in range(7):
                for c in range(7):
                    if r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4):
                        set_func(start_r + r, start_c + c, True)
                    else:
                        set_func(start_r + r, start_c + c, False)
            # Separators
            for r in range(-1, 8):
                for c in range(-1, 8):
                    nr, nc = start_r + r, start_c + c
                    if 0 <= nr < size and 0 <= nc < size and not reserved[nr][nc]:
                        set_func(nr, nc, False)

        add_finder(0, 0)
        add_finder(0, size - 7)
        add_finder(size - 7, 0)

        # Alignment patterns (for ver >= 2)
        if ver >= 2:
            align_positions = {2: [6, 18], 3: [6, 22], 4: [6, 26]}[ver]
            for ar in align_positions:
                for ac in align_positions:
                    if reserved[ar][ac]:
                        continue
                    for r in range(-2, 3):
                        for c in range(-2, 3):
                            val = (max(abs(r), abs(c)) != 1)
                            set_func(ar + r, ac + c, val)

        # Timing patterns
        for i in range(8, size - 8):
            if not reserved[6][i]:
                set_func(6, i, (i % 2 == 0))
            if not reserved[i][6]:
                set_func(i, 6, (i % 2 == 0))

        # Dark module
        set_func(4 * ver + 9, 8, True)

        # Reserve Format info areas
        for c in range(9):
            if not reserved[8][c]:
                reserved[8][c] = True
        for r in range(9):
            if not reserved[r][8]:
                reserved[r][8] = True
        for c in range(size - 8, size):
            reserved[8][c] = True
        for r in range(size - 7, size):
            reserved[r][8] = True

        # Place data using standard mask 0: (row + col) % 2 == 0
        bit_idx = 0
        all_bits = []
        for byte_val in full_codewords:
            for b_i in range(7, -1, -1):
                all_bits.append((byte_val >> b_i) & 1)

        col = size - 1
        direction = -1  # up
        while col > 0:
            if col == 6:
                col -= 1
            rows = range(size - 1, -1, -1) if direction == -1 else range(size)
            for r in rows:
                for c in (col, col - 1):
                    if not reserved[r][c]:
                        bit = all_bits[bit_idx] if bit_idx < len(all_bits) else 0
                        bit_idx += 1
                        mask = ((r + c) % 2 == 0)
                        matrix[r][c] = bool(bit ^ mask)
            direction = -direction
            col -= 2

        # Format info: EC Level L (01), Mask 0 (000) => 01000
        # Format info with BCH: 01000 -> 0x08 -> BCH error check -> 0x77c4 with mask 0x5412
        format_val = 0b111011111000100
        format_bits = [(format_val >> i) & 1 for i in range(14, -1, -1)]

        # Top-left format bits
        seq1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
        for idx, (r, c) in enumerate(seq1):
            matrix[r][c] = bool(format_bits[idx])

        # Other format bits
        seq2 = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8),
                (size - 5, 8), (size - 6, 8), (size - 7, 8),
                (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5),
                (8, size - 4), (8, size - 3), (8, size - 2), (8, size - 1)]
        for idx, (r, c) in enumerate(seq2):
            matrix[r][c] = bool(format_bits[idx])

        return matrix

    @classmethod
    def to_terminal_string(cls, text: str) -> str:
        """Returns Unicode block characters string representing the QR code with quiet border."""
        matrix = cls.generate_matrix(text)
        size = len(matrix)
        border = 2
        full_size = size + 2 * border
        grid = [[False] * full_size for _ in range(full_size)]
        for r in range(size):
            for c in range(size):
                grid[r + border][c + border] = matrix[r][c]

        lines = []
        # Group pairs of vertical rows into ▀ (top black), ▄ (bottom black), █ (both black), ' ' (both white)
        for r in range(0, full_size, 2):
            line = []
            for c in range(full_size):
                top = grid[r][c]
                bottom = grid[r + 1][c] if r + 1 < full_size else False
                if top and bottom:
                    line.append("█")
                elif top and not bottom:
                    line.append("▀")
                elif not top and bottom:
                    line.append("▄")
                else:
                    line.append(" ")
            lines.append("".join(line))
        return "\n".join(lines)
