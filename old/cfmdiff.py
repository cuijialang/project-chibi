import sys

def diffcfm(fn1, fn2):
    setbits = []
    unsetbits = []

    with open(fn1, 'rb') as f:
        f1 = f.read()

    with open(fn2, 'rb') as f:
        f2 = f.read()

    assert len(f1) == len(f2)

    for byte_i in range(len(f1)):
        byte1 = f1[byte_i]
        byte2 = f2[byte_i]

        if byte1 != byte2:
            for bit_i in range(8):
                bit1 = byte1 & (1 << bit_i)
                bit2 = byte2 & (1 << bit_i)

                if bit1 != bit2:
                    if bit1:
                        unsetbits.append((byte_i, bit_i))
                    else:
                        setbits.append((byte_i, bit_i))

    return (setbits, unsetbits)

def main():
    fn1 = sys.argv[1]
    fn2 = sys.argv[2]

    setbits, unsetbits = diffcfm(fn1, fn2)

    for byte_i, bit_i in setbits:
        print("Bit became   SET at 0x{:04X} bit {} ({:03X})".format(byte_i, bit_i, byte_i - 0xC0 - 3 * 0x380))

    for byte_i, bit_i in unsetbits:
        print("Bit became UNSET at 0x{:04X} bit {} ({:03X})".format(byte_i, bit_i, byte_i - 0xC0 - 3 * 0x380))

if __name__=='__main__':
    main()
