import os
import heapq
import md5
import pickle

from collections import defaultdict
from functools import partial

from nltk.classify import NaiveBayesClassifier, SklearnClassifier, MaxentClassifier
from nltk.metrics import BigramAssocMeasures
from nltk.probability import FreqDist, ConditionalFreqDist
from nltk import collocations
from sklearn.svm import LinearSVC

from get_logger import LOGGER

class SmartPhraseIterator(object):
    def __init__(self, phrases):
        self.phrases = phrases

    def iterate_formatted_text(self, formatter):
        for sentiment, s_phrases in self.phrases.iteritems():
            for phrase in s_phrases:
                yield phrase.get_formatted_text(formatter), sentiment

    def iterate_formatted_words(self, formatter, exc_sentiment=False):
        for text, sentiment in self.iterate_formatted_text(formatter):
            for word in text:
                if exc_sentiment:
                    yield word
                else:
                    yield word, sentiment

    def iterate_features(self, formatter, n_features=None, bigram_analyzer=None):
        for sentiment, s_phrases in self.phrases.iteritems():
            for phrase in s_phrases:
                feats = phrase.get_features(formatter, n_features, bigram_analyzer)
                yield feats, sentiment

class Word(object):
    def __init__(self, word):
        self.word = word

    def get_word(self):
        return self.word

    def get_formatted_word(self, formatter):
        return formatter.process_word(self.word)

class BigramAnalyzer(object):
    def __init__(self, bigrams):
        self.formatted_bigrams = self._format_bigram(bigrams)

    def find_bigrams_for(self, word):
        return self.formatted_bigrams[word]

    def scan_features_for_bigrams(self, features):
        res = []
        for i, word in enumerate(features):
            bg = self.find_bigrams_for(word)
            if bg:
                try:
                    next_word = features[i+1]
                    if next_word in bg:
                        res.append((word, next_word))
                except IndexError:
                    return res
        return res

    def _format_bigram(self, bigrams):
        res = defaultdict(list)
        for term1, term2 in bigrams:
            res[term1].append(term2)
        return res

class Phrase(object):
    def __init__(self, text, tokenizer):
        self.words = [Word(w) for w in tokenizer(text)]

    def get_text(self):
        return ' '.join([w.get_word() for w in self.words])

    def get_formatted_text(self, formatter):
        return filter(None, [w.get_formatted_word(formatter)
            for w in self.words])

    def get_features(self, formatter, n_features=None, bigram_analyzer=None):
        formatted_text = self.get_formatted_text(formatter)

        res = {}
        for word_i, word in enumerate(formatted_text):

            # Single features
            can_add = n_features == None or word in n_features
            if can_add:
               res['has(%s)' % word] = True

        if bigram_analyzer:
            bigrams = bigram_analyzer.scan_features_for_bigrams(formatted_text)
            for terma, termb in bigrams:
                res['has(%s,%s)' % (terma, termb)] = True

        return res

class TextProcessor(object):
    def __init__(self, phrases, formatter):
        self.formatter = formatter

        self.phrases = phrases
        self.phrases_it = SmartPhraseIterator(self.phrases)

    def _get_class_sentiments(self):
        return self.phrases.keys()

    def get_bigram_analyzer(self, n, words):
        LOGGER.info("Building Bigram Analyzer")
        bigram_measures = collocations.BigramAssocMeasures()
        finder = collocations.BigramCollocationFinder.from_words(words)
        return BigramAnalyzer(finder.above_score(bigram_measures.likelihood_ratio, n))

    def _build_prob_dist(self, fd, cfd):
        LOGGER.info("Building frequency distribution")
        for word, sentiment in self.phrases_it.iterate_formatted_words(self.formatter):
            fd.inc(word)
            cfd[sentiment].inc(word)
        return fd, cfd

    def _get_most_informative_features(self, nfeats,
                            freq_dist, cond_freq_dist):

        LOGGER.info("Getting most informative fearures")

        LOGGER.info("Building Heap")
        heap = []
        smallest_score = -1

        res = []
        for word, total_freq in freq_dist.iteritems():
            score = 0
            for sentiment in self._get_class_sentiments():
                score += BigramAssocMeasures.chi_sq(
                    cond_freq_dist[sentiment][word],
                    (total_freq, cond_freq_dist[sentiment].N()),
                    freq_dist.N()
                )

                if len(heap) < nfeats:
                    heapq.heappush(heap, (score, word))
                    if score < smallest_score:
                        smallest_score = score
                elif score > smallest_score:
                    smallest_score = score
                    heapq.heapreplace(heap, (score, word))
                    LOGGER.info("Smallest score has increased to: %s" % smallest_score)

        sorted_res = []
        while heap:
            score, word = heapq.heappop(heap)
            sorted_res.insert(0, word)
        return sorted_res

    def train_classifier(self, formatter, n_bigrams, n_feats, meta= {}):
        freq_dist, cond_freq_dist = self._build_prob_dist(FreqDist(),
                                                ConditionalFreqDist())
        feats = self._get_most_informative_features(n_feats, freq_dist,
                                                                    cond_freq_dist)
        bigrams = self.get_bigram_analyzer(n_bigrams, freq_dist.iterkeys())

        meta['n_bigrams'] = n_bigrams
        meta['n_feats'] = n_feats

        LOGGER.info("Building TrainedClassifier")
        return TrainedClassifier(formatter, bigrams, feats, meta,
                            phrases_iterator=self.phrases_it)

class TrainedClassifier(object):
    CLASSIFIERS = {
        'NaiveBayes': NaiveBayesClassifier.train,
        'SVM': lambda d: SklearnClassifier(LinearSVC()).train(list(d)),
        'Maxent': lambda d: MaxentClassifier.train(list(d), algorithm='iis')
    }

    @staticmethod
    def load(s_dir, formatter):
        with open(os.path.join(s_dir, 'classifier.pickle'), 'r') as classifier:
            with open(os.path.join(s_dir, 'bigrams.pickle'), 'r') as bigrams:
                with open(os.path.join(s_dir, 'feats.pickle'), 'r') as feats:
                    with open(os.path.join(s_dir, 'meta.pickle'), 'r') as meta:
                        classifier = pickle.loads(classifier.read())
                        feats = pickle.loads(feats.read())
                        bigrams = pickle.loads(bigrams.read())
                        meta = pickle.loads(meta.read())
                        return TrainedClassifier(formatter, bigrams, feats,
                                                meta, classifier=classifier)

    def __init__(self, formatter, bigrams, feats, meta, phrases_iterator = None, classifier= None):
        self.formatter = formatter
        self.bigrams = bigrams
        self.feats = feats
        self.meta = meta

        if phrases_iterator:
            training_set = phrases_iterator.iterate_features(self.formatter, self.feats,
                                                        self.bigrams)
            self.classifier = self.CLASSIFIERS[self.meta['classifier_type']](training_set)
        elif classifier:
            self.classifier = classifier
        else:
            raise Exception("No classifier provided")

    def show_most_informative_features(self, *args, **kwargs):
        return self.classifier.show_most_informative_features(*args, **kwargs)

    def get_components(self):
        return self.bigrams, self.feats

    def _phrase_to_feature_vector(self, phrase):
        res = phrase.get_features(self.formatter, self.feats, self.bigrams)
        if len(res.keys()) < 1:
            return None
        return res

    def batch_classify(self, phrases):
        return map(self.classify, phrases)

    def classify(self, phrase):
        feature_vector = phrase.get_features(self.formatter, self.feats,
            self.bigrams)
        if feature_vector:
            return self.classifier.classify(feature_vector)
        return None

    def prob_classify(self, phrase):
        feature_vector = phrase.get_features(self.formatter, self.feats,
            self.bigrams)
        if feature_vector:
            return self.classifier.prob_classify(feature_vector)
        return None

    def get_uid(self):
        return md5.md5(str(self.meta)).hexdigest()

    def serialize(self, s_dir, serializer=pickle, write_function=open):
        to_write = {
            os.path.join(s_dir, 'classifier.pickle'): self.classifier,
            os.path.join(s_dir, 'bigrams.pickle'): self.bigrams,
            os.path.join(s_dir, 'meta.pickle'): self.meta,
            os.path.join(s_dir, 'feats.pickle'): self.feats
        }
        for path, obj in to_write.iteritems():
            with write_function(path, 'w') as f:
                serializer.dump(obj, f)
