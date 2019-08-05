import re

class WithOffsets():
    """ Helper mixin for models that use offsets. Assumes the existence
    of a +offset_list+ attribute which contains a space-separated list of offset:length pairs.
    NOTE(kilemensi): Looks like offset pairs are now ':' separated and they are (offset, length)
    """
    # SPACE_RE = re.compile(r' +')
    SPACE_RE = re.compile(r'[( )]')

    def offsets(self):
        """ Get an ordered list of +(offset, length)+ tuples of occurrences
        of this entity in the original document text. May be empty. """
        offsets = self.SPACE_RE.sub('', self.offset_list or '')
        offsets = [v.split(',') for v in offsets.split(':')]
        return sorted((int(pair[0]), int(pair[1])) for pair in offsets if pair and pair[0])


    def add_offset(self, pair):
        """ Add an (offset, length) pair to the offset list. Returns true if
        it was added, false if it was already there. """
        if pair in self.offsets():
            return False

        self.offset_list = ((self.offset_list or '') + " {}:{}".format(pair, pair)).strip()
        return True

    def add_offsets(self, pairs):
        """ Add many occurrences, returning True if any where added. """
        added = False
        for p in pairs:
            added |= self.add_offset(p)
        return added


