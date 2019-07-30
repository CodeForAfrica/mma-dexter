import unittest
import datetime

from werkzeug.datastructures import FileStorage

from dexter.attachments import HttpExposedFileSystemStore, S3Store
from dexter.models import Document, DocumentAttachment, AttachmentImage, db, Author, Country, Medium
from dexter.models.seeds import seed_db

from tests.fixtures import dbfixture, DocumentData

class TestAttachments(unittest.TestCase):
    def setUp(self):
        self.db = db
        self.db.drop_all()
        self.db.create_all()
        seed_db(db)

        self.fx = dbfixture.data(DocumentData)
        self.fx.setup()


    def tearDown(self):
        self.fx.teardown()
        self.db.session.remove()
        self.db.drop_all()

    def test_s3_path(self):
        store = S3Store('foo', 'a', 'b', prefix='p')

        self.assertEqual(store.get_key("attachment", "1/foo.pdf", 0, 0, 'application/pdf'), "p/attachment/1/foo.pdf")
        self.assertEqual(store.get_key("attachment", 5, 10, 50, 'image/png'), "p/attachment/5/10x50.png")

    def test_fs_path(self):
        store = HttpExposedFileSystemStore('foo', '/prefix')

        self.assertEqual(':'.join(store.get_path("attachment", "1/foo.pdf", 0, 0, 'application/pdf')),
            "attachment:1:0:1.0x0.pdf")

    def test_delete_attachments(self):
        doc = Document.query.get(self.fx.DocumentData.simple.id)

        with open("tests/fixtures/smiley.png") as f:
            upload = FileStorage(f, 'smiley.png', name='file', content_type='image/png')
            attachment = DocumentAttachment.from_upload(upload, None)
            attachment.document = doc
            db.session.commit()
            self.assertEqual('image/png', attachment.image.original.mimetype)

        doc = Document.query.get(doc.id)
        x = list(doc.attachments)
        for att in x:
          for y in att.image:
            print((1))
          #print [1 for t in att.image]
          pass

        self.assertEqual(1, len(doc.attachments))
        doc.attachments = []

        db.session.commit()

        self.assertEqual(0, len(doc.attachments))
