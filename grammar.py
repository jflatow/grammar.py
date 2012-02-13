"""
A miniature parsing library.

>>> grammar = Grammar({'constant':   Terminal(r'[\d]+\.?[\d]*'),     \
                       'variable':   Terminal(r'[A-Za-z]+'),         \
                       'operator':   Terminal.padded(r'[\+\-\*\/]'), \
                       'operand':    Pipe('constant', 'variable'),   \
                       'expression': Seq('operand', 'operator', 'operand')})

>>> valid = ['a + b', 'c - d', '5 * 4', 'z / 1']
>>> invalid = ['$any', 'any', 'a! + n', '&']

>>> [grammar.parse('expression', v) for v in valid]
[(expression, (operand, variable, 'a'), (operator, ' + '), (operand, variable, 'b')),\
 (expression, (operand, variable, 'c'), (operator, ' - '), (operand, variable, 'd')),\
 (expression, (operand, constant, '5'), (operator, ' * '), (operand, constant, '4')),\
 (expression, (operand, variable, 'z'), (operator, ' / '), (operand, constant, '1'))]

>>> [grammar.is_valid('expression', i) for i in invalid]
[False, False, False, False]
"""
import re

class BadGrammar(Exception): pass
class BadState(Exception):
    def __str__((expected, string, start)):
        return "Expected %s but got '%s' >>> '%s'" % (expected,
                                                      string[:start].replace("\'", "\\'"),
                                                      string[start:].replace("\'", "\\'"))

class Grammar(dict):
    def __init__(self, *args, **kwargs):
        super(type(self), self).__init__(*args, **kwargs)
        for name, pattern in self.items():
            pattern.name = name

    def __getitem__(self, state_or_name):
        if isinstance(state_or_name, State):
            return state_or_name
        return super(type(self), self).__getitem__(state_or_name)

    def is_valid(self, name, string):
        try:
            return self.parse(name, string) and True
        except BadState:
            return False

    def parse(self, name, string):
        matches = list(self[name].matches(self, string))
        if len(matches) > 1:
            raise BadGrammar(matches)
        if len(matches) < 1:
            raise BadState(self, string, 0)
        which, _end = matches[0]
        return which

class State(tuple):
    name = None

    def __new__(cls, *pattern):
        return tuple.__new__(cls, pattern or (Empty(),))

    def __iter__(self):
        # tupleiterator has no send, so wrap the default with a generator
        for item in tuple.__iter__(self):
            yield item

    def __repr__(self):
        return self.name or "%s%s" %  (type(self).__name__, tuple.__repr__(self))

class Terminal(State):
    def __new__(cls, *pattern):
        return tuple.__new__(cls, (re.compile(''.join(pattern)),))

    def __repr__(self):
        return self.name or "%s('%s')" %  (type(self).__name__, self[0].pattern)

    @classmethod
    def padded(cls, pattern):
        return cls(r'\s*%s\s*' % pattern)

    def matches(self, grammar, string, start=0):
        match = self[0].match(string, start)
        if match is None:
            raise BadState(self, string, start)
        yield (self, match.group()), match.end()

class Empty(Terminal):
    def matches(self, grammar, string, start=0):
        yield (self, ''), start

class Symbolic(State):
    pass

class Seq(Symbolic):
    def matches(self, grammar, string, start=0):
        # initialize the sequence with an empty match at the beginning of the string
        matches = [((), start)]
        for pattern in self:
            # compute every possible match continuation
            matches = [(which + (which_,), end_)
                       for which, end in matches
                       for which_, end_ in grammar[pattern].matches(grammar, string, start=end)]
        for which, end in matches:
            yield ((self,) + which), end

class Pipe(Symbolic):
    def matches(self, grammar, string, start=0):
        # get a (possibly infinite) generator of choices
        choices = iter(self)
        pattern = choices.send(None)
        # this is a BadState unless at least one pattern matches
        matched = False
        while True:
            try:
                # get the matches for the pattern
                matches = list(grammar[pattern].matches(grammar, string, start=start))
                for which, end in matches:
                    yield ((self,) + which), end
                # we got one
                matched = True
            except BadState, e:
                matches = None
            try:
                # get the next pattern, given the last pattern matches
                # patterns decide when they are exhausted
                pattern = choices.send(matches)
            except StopIteration:
                # no more patterns
                if not matched:
                    raise BadState(self, string, start)
                raise StopIteration

class Star(Pipe):
    def __iter__(self):
        pattern = (Empty(),)
        while (yield pattern):
            pattern += self

class Plus(Pipe):
    def __iter__(self):
        pattern = self
        while (yield pattern):
            pattern += self
