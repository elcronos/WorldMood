import functools
import re

import nltk

HASHTAG_RE = re.compile('#\w*[a-zA-Z_]+\w*')
NAME_RE = re.compile('@[A-Za-z0-9]+')
NONCHAR_RE = re.compile('[^a-z]')
START_WITH_SPACE_RE = re.compile('^\s+')
END_WITH_SPACE_RE = re.compile('\s+$')
GRUBER_URLINTEXT_PAT = re.compile(ur'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')

MIN_CHARS= 2

HTML_ENTITIES = {
  '&': '&amp;',
  '>': '&gt;',
  '<': '&lt;',
  '"': '&quot;',
  "'": '&#39;'
};

def _finalize_stripping(text):
    stripped_text= text
    for _re in [START_WITH_SPACE_RE, END_WITH_SPACE_RE]:
        stripped_text = _re.sub('', stripped_text)
    return stripped_text.replace('  ', ' ')

def _strip_re(context_re, text):
    stripped_text= context_re.sub('', text)
    return _finalize_stripping(stripped_text)

strip_urls = functools.partial(_strip_re, GRUBER_URLINTEXT_PAT)
strip_hashtags = functools.partial(_strip_re, HASHTAG_RE)
strip_names = functools.partial(_strip_re, NAME_RE)

def strip_nonchars(text):
    return NONCHAR_RE.sub('', text)

def replace_html_entities(text):
    stripped_text= text
    for to_replace, to_match in HTML_ENTITIES.iteritems():
        stripped_text = stripped_text.replace(to_match, to_replace)
    return _finalize_stripping(stripped_text)

def remove_noise(text, stopwords):

    tokens = nltk.wordpunct_tokenize(text)
    filtered_tokens = filter(lambda w: w not in stopwords and len(w) > MIN_CHARS, tokens)
    return ' '.join(filtered_tokens)

def remove_repetitons(text):
    res = []
    count = 0
    last_char = None

    for c in text:
        if c == last_char:
            if count < 1:
                res.append(c)
                count += 1
        else:
            res.append(c)
            last_char = c
            count = 0
    
    return ''.join(res)

    def _chunk(word):
        i = len(word)-1
        last_char = None
        while i > 0:
            current_char = word[i]
            if not last_char:
                last_char = current_char
            else:
                if current_char == last_char:
                    i -= 1
                else:
                    break
        return word[0:i+2]

    return ' '.join(map(_chunk, tokens))

def make_lowercase(text):
    return text.lower()

def stem_words(text, stemmer):
    tokens = nltk.wordpunct_tokenize(text)
    return ' '.join(map(stemmer.stem, tokens))

def lemmatize_words(text, lemmatizer):
    tokens = nltk.wordpunct_tokenize(text)
    return ' '.join(map(lemmatizer.lemmatize, tokens))

class FormatterPipeline:
    def __init__(self, *formatters):
        self.formatters = formatters

    def process_word(self, word):
        res = word
        for formatter in self.formatters:
            res = formatter(res)
            if not res:
                return None
        return res

    def process(self, text):
        return reduce(lambda t, fm: fm(t), self.formatters, text)
