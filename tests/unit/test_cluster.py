import unittest
import datetime

from dexter.models import Document, Cluster, db, Author, Medium, Country
from dexter.models.seeds import seed_db

from tests.fixtures import dbfixture, AuthorData


class TestCluster(unittest.TestCase):
    def setUp(self):
        self.db = db
        self.db.drop_all()
        self.db.create_all()
        seed_db(db)

        self.fx = dbfixture.data(AuthorData)
        self.fx.setup()

    def tearDown(self):
        # delete all docs to prevent fixture deletion from going awry
        for d in Document.query.all():
            db.session.delete(d)
        self.db.session.commit()

        self.fx.teardown()
        self.db.session.rollback()
        self.db.session.remove()
        self.db.drop_all()

    def make_docs(self):
        docs = [Document(url='foo-{}'.format(i)) for i in range(3)]
        for d in docs:
            d.published_at = datetime.datetime.now()
            d.medium = Medium.query.first()
            d.author = Author.query.first()
            d.country = Country.query.first()

        # get ids
        db.session.add_all(docs)
        db.session.flush()
        return docs

    def test_find_or_create(self):
        docs = self.make_docs()

        cluster = Cluster.find_or_create(docs=docs)
        self.assertEqual(cluster.fingerprint, '202cb962ac59075b964b07152d234b70')
        self.assertEqual(sorted(cluster.documents), sorted(docs))

        db.session.add(cluster)
        db.session.flush()

        cluster2 = Cluster.find_or_create(docs=docs)
        self.assertIsNotNone(cluster2.id)
        self.assertEqual(cluster.id, cluster2.id)

    def test_delete_cascades(self):
        docs = self.make_docs()

        cluster = Cluster.find_or_create(docs=docs)
        db.session.add(cluster)
        db.session.flush()

        deleted = docs[0]
        rest = docs[1:]

        db.session.delete(deleted)
        db.session.flush()
        db.session.commit()

        cluster = db.session.query(Cluster).filter(Cluster.id == cluster.id).one()
        self.assertEqual(sorted(rest), sorted(cluster.documents))
