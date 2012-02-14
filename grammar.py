"""
A miniature parsing library.

>>> grammar = Grammar({'eof':        Terminal(r'$'),                              \
                       'semicolon':  Terminal.padded(r';'),                       \
                       'constant':   Terminal(r'[\d]+\.?[\d]*'),                  \
                       'variable':   Terminal(r'[A-Za-z]+'),                      \
                       'operator':   Terminal.padded(r'[\+\-\*\/]'),              \
                       'operand':    Pipe('constant', 'variable'),                \
                       'expression': Seq('operand', Star('operator', 'operand')), \
                       'block':      Seq(Plus('expression', 'semicolon'), 'eof')})

>>> valid = ['a+b; c+d;', 'c - d;', '5 * 4;', 'z / 1;']
>>> invalid = ['$any', 'any +', 'a! + n', '&']

>>> [grammar.parse('block', v) for v in valid]   #doctest: +NORMALIZE_WHITESPACE
[('block', [[('expression', [('operand', (variable, 'a')), [(operator, '+'), ('operand', (variable, 'b'))]]), (semicolon, '; '),
             ('expression', [('operand', (variable, 'c')), [(operator, '+'), ('operand', (variable, 'd'))]]), (semicolon, ';')], (eof, '')]), \
 ('block', [[('expression', [('operand', (variable, 'c')), [(operator, ' - '), ('operand', (variable, 'd'))]]), (semicolon, ';')], (eof, '')]),\
 ('block', [[('expression', [('operand', (constant, '5')), [(operator, ' * '), ('operand', (constant, '4'))]]), (semicolon, ';')], (eof, '')]),\
 ('block', [[('expression', [('operand', (variable, 'z')), [(operator, ' / '), ('operand', (constant, '1'))]]), (semicolon, ';')], (eof, '')])]
>>> [grammar.is_valid('block', i) for i in invalid]
[False, False, False, False]
"""
import re

class BadGrammar(Exception): pass
class BadState(Exception):
    def __str__((expected, string, start)):
        return "Expected %r but got:\n\t%s" % (expected, string[start:])

class Grammar(dict):
    def __init__(self, *args, **kwargs):
        super(type(self), self).__init__(*args, **kwargs)
        for name, pattern in self.items():
            pattern.name = name

    def __getitem__(self, state_or_name):
        if isinstance(state_or_name, State):
            return state_or_name
        return super(type(self), self).__getitem__(state_or_name)

    def __repr__(self):
        return '{%s}' % ', '.join('%r: %s' % item for item in self.items())

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
            raise BadState(self[name], string, 0)
        which, _end = matches[0]
        return which

class State(tuple):
    name = None

    def __new__(cls, *pattern):
        return tuple.__new__(cls, pattern or (Empty(),))

    def __iter__(self): # tupleiterator has no send, so wrap it with a generator
        for item in tuple.__iter__(self):
            yield item

    def __repr__(self):
        return self.name or str(self)

    def __str__(self):
        return '%s(%s)' % (type(self).__name__, ', '.join(repr(p) for p in self))

class Terminal(State):
    def __new__(cls, *pattern):
        return tuple.__new__(cls, (re.compile(''.join(pattern)),))

    def __str__(self):
        return "r'%s'" % self[0].pattern.replace("\\'", "\\\\'").replace("'", "\\'")

    @classmethod
    def padded(cls, pattern):
        return cls(r'\s*%s\s*' % pattern)

    def matches(self, grammar, string, start=0):
        match = self[0].match(string, start)
        if match is None:
            raise BadState(self, string, start)
        yield (self, match.group()), match.end()

class Empty(Terminal):
    def __str__(self):
        return 'Empty'

    def matches(self, grammar, string, start=0):
        yield None, start

class Symbolic(State): pass
class Seq(Symbolic):
    def fold(self, match):
        if self.name:
            return self.name, [m for m in match if m]
        return [m for m in match if m]

    def matches(self, grammar, string, start=0):
        errlist = [BadState(self, string, start)]
        matches = [((), start)]
        for pattern in self:
            def continuations(which, end):
                try:
                    for which_, end_ in grammar[pattern].matches(grammar, string, start=end):
                        yield (which + (which_,)), end_
                except BadState, e:
                    errlist.append(e)
            matches = [c for match in matches for c in continuations(*match)]
            if not matches:
                raise errlist[-1]
        for which, end in matches:
            yield self.fold(which), end

class Pipe(Symbolic):
    def fold(self, match):
        if self.name:
            return self.name, match
        return match

    def matches(self, grammar, string, start=0):
        choices = iter(self)         # could be infinite, like Star or Plus
        pattern = choices.send(None)
        matched = []
        while True:
            try:
                for which, end in grammar[pattern].matches(grammar, string, start=start):
                    yield self.fold(which), end
                matched.append(True)
            except BadState, e:
                matched.append(None)
            try:
                pattern = choices.send(matched[-1])
            except StopIteration:
                if not any(matched):
                    raise BadState(self, string, start)
                raise StopIteration

class Star(Pipe):
    def __iter__(self):
        pattern = Seq()
        while (yield pattern):
            pattern = Seq(*(pattern + self))

class Plus(Pipe):
    def __iter__(self):
        pattern = Seq(*self)
        while (yield pattern):
            pattern = Seq(*(pattern + self))
