import unittest
import datetime

from dexter.models import Document, DocumentEntity, Entity, Utterance, DocumentKeyword, DocumentPlace, db
from dexter.models.seeds import seed_db

from tests.fixtures import dbfixture, DocumentData


class TestDocument(unittest.TestCase):
    def setUp(self):
        self.db = db
        self.db.drop_all()
        self.db.create_all()
        seed_db(db)

        self.fx = dbfixture.data(DocumentData)
        self.fx.setup()

        self.doc = Document.query.get(self.fx.DocumentData.simple.id)

    def tearDown(self):
        self.db.session.remove()

        self.fx.teardown()
        self.db.drop_all()

    def test_add_keyword_no_dups(self):
        doc = self.doc

        k = DocumentKeyword(keyword='foo')
        self.assertTrue(doc.add_keyword(k))

        self.assertTrue(doc.add_keyword(DocumentKeyword(keyword='gout')))
        # shouldn't work
        self.assertFalse(doc.add_keyword(DocumentKeyword(keyword='go\xfbt')))

    def test_add_entities_no_dups(self):
        doc = self.doc

        e = Entity()
        e.group = 'group'
        e.name = 'name'

        de = DocumentEntity()
        de.entity = e
        de.relevance = 1.0
        de.count = 2

        doc.add_entity(de)
        self.assertEqual([de], list(doc.entities))

        e2 = Entity()
        e2.group = 'group'
        e2.name = 'name'

        de2 = DocumentEntity()
        de2.entity = e
        de2.relevance = 0.5
        de2.count = 3

        doc.add_entity(de2)
        # shouldn't add dup
        self.assertEqual([de], list(doc.entities))

    def test_add_utterance(self):
        doc = self.doc
        doc.text = 'And Fred said "Hello" to everyone.'

        u = Utterance()
        u.entity = Entity()
        u.entity.group = 'person'
        u.entity.name = 'Fred'
        u.quote = 'Hello'

        self.assertTrue(doc.add_utterance(u))
        self.assertTrue(u in doc.utterances)

        # can't add twice
        self.assertFalse(doc.add_utterance(u))
        self.assertEqual(1, len(doc.utterances))

    def test_add_utterance_similar(self):
        doc = self.doc
        doc.text = 'And Fred said "Hello there guys," to everyone.'

        u = Utterance()
        u.entity = Entity()
        u.entity.group = 'person'
        u.entity.name = 'Fred'
        u.quote = 'Hello there guys'

        self.assertTrue(doc.add_utterance(u))
        self.assertTrue(u in doc.utterances)

        # can't add similar quotations twice
        u2 = Utterance()
        u2.entity = Entity()
        u2.entity.group = 'person'
        u2.entity.name = 'Fred'
        u2.quote = '\"Hello there guys,\" ...'

        self.assertFalse(doc.add_utterance(u2))
        self.assertEqual(1, len(doc.utterances))

    def test_add_utterance_update_offset(self):
        doc = self.doc
        doc.text = 'And Fred said "Hello" to everyone.'

        u = Utterance()
        u.entity = Entity()
        u.entity.group = 'person'
        u.entity.name = 'Fred'
        u.quote = 'Hello'
        self.assertTrue(doc.add_utterance(u))

        u2 = Utterance()
        u2.entity = Entity()
        u2.entity.group = 'person'
        u2.entity.name = 'Fred'
        u2.quote = 'Hello'
        u2.offset = 10
        u2.length = 5

        self.assertTrue(doc.add_utterance(u2))
        self.assertEqual(10, u.offset)
        self.assertEqual(5, u.length)

        self.assertFalse(doc.add_utterance(u2))

    def test_delete_document(self):
        doc = self.doc
        doc.text = 'And Fred said "Hello" to everyone.'
        doc.published_at = datetime.datetime.utcnow()

        u = Utterance()
        u.entity = Entity()
        u.entity.group = 'person'
        u.entity.name = 'Fred'
        u.quote = 'Hello'
        self.assertTrue(doc.add_utterance(u))

        de = DocumentEntity()
        de.document = doc
        de.relevance = 0.5
        de.entity = Entity.query.first()

        self.db.session.add(doc)
        self.db.session.commit()

        self.db.session.delete(doc)
        self.db.session.commit()

    def test_place_relevance(self):
        dp1 = DocumentPlace(relevance=0.2)
        dp2 = DocumentPlace(relevance=0.8)
        dp3 = DocumentPlace()

        doc = self.doc
        doc.places = [dp1, dp2, dp3]

        self.assertAlmostEqual(doc.places_relevance_threshold(), 0.5, 3)

    def test_keyword_relevance(self):
        dk1 = DocumentKeyword(relevance=0.2)
        dk2 = DocumentKeyword(relevance=0.8)
        dk3 = DocumentKeyword()

        doc = self.doc
        doc.keywords = [dk1, dk2, dk3]

        self.assertAlmostEqual(doc.keyword_relevance_threshold(), 0.5, 3)

    def test_word_count(self):
        d = Document()

        d.text = "    test \n  \t one"
        self.assertEqual(d.word_count, 2)

        d.text = "    test \n  \t"
        self.assertEqual(d.word_count, 1)

        d.text = ""
        self.assertEqual(d.word_count, 0)

        d.text = None
        self.assertIsNone(d.word_count)
