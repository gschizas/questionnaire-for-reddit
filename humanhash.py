"""
humanhash: Human-readable representations of digests.

The simplest ways to use this module are the :func:`humanize` and :func:`uuid`
functions. For tighter control over the output, see :class:`HumanHasher`.
"""

import operator
import uuid as uuidlib
from functools import reduce

DEFAULT_WORDLIST = (
    'ack', 'alanine', 'albania', 'alpha', 'angel', 'apart', 'april', 'armenia', 'artist', 'asparagus', 'aspen',
    'august', 'austria', 'autumn', 'avocado', 'bacon', 'bakerloo', 'batman', 'beer', 'belarus', 'belgium', 'berlin',
    'beryllium', 'black', 'blossom', 'blue', 'bluebird', 'bosnia', 'bravo', 'bulgaria', 'bulldog', 'burger', 'butter',
    'carbon', 'cardinal', 'carolina', 'carpet', 'cat', 'ceiling', 'charlie', 'chicken', 'coffee', 'cola', 'cold',
    'comet', 'crazy', 'cup', 'cyprus', 'czechia', 'dakota', 'december', 'delta', 'denmark', 'diet', 'don', 'double',
    'early', 'earth', 'east', 'echo', 'edward', 'eight', 'eighteen', 'eleven', 'emma', 'enemy', 'england', 'equal',
    'estonia', 'failed', 'fanta', 'fifteen', 'fillet', 'finch', 'finland', 'fish', 'five', 'fix', 'floor', 'football',
    'four', 'fourteen', 'foxtrot', 'france', 'freddie', 'friend', 'fruit', 'gee', 'georgia', 'germany', 'glucose',
    'golf', 'greece', 'green', 'grey', 'hamper', 'happy', 'harry', 'helium', 'high', 'hot', 'hotel', 'hungary',
    'hydrogen', 'india', 'indigo', 'ink', 'ireland', 'island', 'italy', 'item', 'jersey', 'jig', 'johnny', 'juliet',
    'july', 'jupiter', 'kilo', 'king', 'kitten', 'lactose', 'lake', 'lamp', 'latvia', 'lemon', 'leopard', 'lima',
    'lion', 'lithium', 'lithuania', 'london', 'low', 'luxembourg', 'magazine', 'magnesium', 'mango', 'march', 'mars',
    'may', 'mexico', 'mike', 'mirror', 'mobile', 'mockingbird', 'moldova', 'monkey', 'moon', 'mountain', 'muppet',
    'music', 'neptune', 'netherlands', 'network', 'nine', 'nineteen', 'nitrogen', 'north', 'norway', 'november', 'nuts',
    'october', 'one', 'orange', 'oranges', 'oscar', 'oven', 'oxygen', 'papa', 'paris', 'pasta', 'pip', 'pizza', 'pluto',
    'poland', 'portugal', 'potato', 'princess', 'purple', 'quebec', 'queen', 'quiet', 'red', 'river', 'robert', 'robin',
    'romania', 'romeo', 'rugby', 'russia', 'sad', 'salami', 'saturn', 'scotland', 'september', 'serbia', 'seven',
    'seventeen', 'shade', 'sierra', 'single', 'sink', 'six', 'sixteen', 'skylark', 'slovakia', 'slovenia', 'snake',
    'social', 'sodium', 'solar', 'south', 'spaghetti', 'spain', 'speaker', 'spring', 'stairway', 'steak', 'stream',
    'summer', 'sweden', 'sweet', 'switzerland', 'table', 'tango', 'ten', 'tennis', 'thirteen', 'three', 'timing',
    'triple', 'turkey', 'twelve', 'twenty', 'two', 'ukraine', 'uncle', 'undress', 'uniform', 'uranus',
    'vegan', 'venus', 'victor', 'video', 'violet', 'west', 'whiskey', 'white', 'william', 'winner', 'winter', 'wolfram',
    'xray', 'yankee', 'yellow', 'zebra', 'zulu')


class HumanHasher(object):
    """
    Transforms hex digests to human-readable strings.

    The format of these strings will look something like:
    `victor-bacon-zulu-lima`. The output is obtained by compressing the input
    digest to a fixed number of buff, then mapping those buff to one of 256
    words. A default wordlist is provided, but you can override this if you
    prefer.

    As long as you use the same wordlist, the output will be consistent (i.e.
    the same digest will always render the same representation).
    """

    def __init__(self, wordlist=DEFAULT_WORDLIST):
        if len(wordlist) != 256:
            raise ValueError("Wordlist must have exactly 256 items")
        self.wordlist = wordlist

    def humanize(self, hexdigest, words=4, separator='-'):
        """
        Humanize a given hexadecimal digest.

        Change the number of words output by specifying `words`. Change the
        word separator with `separator`.

            >>> digest = '60ad8d0d871b6095808297'
            >>> HumanHasher().humanize(digest)
            'sodium-magnesium-nineteen-hydrogen'
        """

        # Gets a list of byte values between 0-255.
        buff = [int(x,16) for x in map(''.join, zip(hexdigest[::2], hexdigest[1::2]))]
        # Compress an arbitrary number of buff to `words`.
        compressed = compress(buff, words)
        # Map the compressed byte values through the word list.
        return separator.join(self.wordlist[byte] for byte in compressed)

    def uuid(self, **params):
        """
        Generate a UUID with a human-readable representation.

        Returns `(human_repr, full_digest)`. Accepts the same keyword arguments
        as :meth:`humanize` (they'll be passed straight through).
        """

        digest = str(uuidlib.uuid4()).replace('-', '')
        return self.humanize(digest, **params), digest


def compress(buffer, target):
    """
    Compress a list of byte values to a fixed target length.

        >>> buff = [96, 173, 141, 13, 135, 27, 96, 149, 128, 130, 151]
        >>> HumanHasher.compress(buff, 4)
        [205, 128, 156, 96]

    Attempting to compress a smaller number of buff to a larger number is
    an error:

        >>> HumanHasher.compress(buff, 15)  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        ValueError: Fewer input buff than requested output
    """

    length = len(buffer)
    if target > length:
        raise ValueError("Fewer input buff than requested output")

    # Split `buff` into `target` segments.
    seg_size = length // target
    segments = [buffer[i * seg_size:(i + 1) * seg_size]
                for i in range(target)]
    # Catch any left-over buff in the last segment.
    segments[-1].extend(buffer[target * seg_size:])

    # Use a simple XOR checksum-like function for compression.
    checksum = lambda buff: reduce(operator.xor, buff, 0)
    checksums = map(checksum, segments)
    return checksums


DEFAULT_HASHER = HumanHasher()
uuid = DEFAULT_HASHER.uuid
humanize = DEFAULT_HASHER.humanize
