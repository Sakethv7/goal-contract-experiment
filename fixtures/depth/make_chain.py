"""Writes a serial chain of files. Each file holds filler text and the name of the next file. Contract: docs/api.md, Contract 23."""
import random
from pathlib import Path

WORDS = ("amber basil cedar dune ember fjord glade harbor iris jade kelp lumen mesa nectar onyx pearl quartz reed sable "
         "tundra umber vale willow xenon yarrow zephyr").split()
FILE_BYTES = 5000


def make_chain(dest: Path, length: int, seed: int) -> str:
    """Creates dest/chain/start.txt and `length` files in all. Returns the code word in the last file."""
    rng = random.Random(seed)
    chain = Path(dest) / "chain"
    chain.mkdir(parents=True, exist_ok=True)
    names = ["start.txt"] + [f"{rng.getrandbits(40):010x}.txt" for _ in range(length - 1)]
    codeword = f"{rng.choice(WORDS)}-{rng.randint(1000, 9999)}"
    for i, name in enumerate(names):
        filler = []
        while sum(len(w) + 1 for w in filler) < FILE_BYTES:
            filler.append(rng.choice(WORDS))
        body = " ".join(filler)
        tail = f"CODEWORD: {codeword}" if i == length - 1 else f"NEXT: chain/{names[i + 1]}"
        (chain / name).write_text(body + "\n" + tail + "\n")
    return codeword
