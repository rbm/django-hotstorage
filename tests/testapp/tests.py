from django.test import TestCase
from redis import Redis

from models import Person, PhoneNumber

class HotStorageTests(TestCase):
    def setUp(self):
        Redis().flushall()
        p1 = Person(name='Test User 1', ssn='123456789')
        p1.save()
        pn1 = PhoneNumber(person=p1, label='Test 1', phone_number='5558675309')
        pn1.save()
        from django import db
        db.reset_queries()

    def test_get_existing(self):
        from django.conf import settings
        from django import db
        settings.DEBUG = True

        p = Person.objects.get(pk=1)
        self.assertEqual(p.name, 'Test User 1')
        self.assertEqual(len(db.connection.queries), 0)

        p = Person.objects.get(ssn='123456789')
        self.assertEqual(p.name, 'Test User 1')
        self.assertEqual(len(db.connection.queries), 0)

        pq = list(Person.objects.all())
        self.assertEqual(len(db.connection.queries), 1)

    def test_get_nonexistant(self):
        from django.conf import settings
        from django import db
        settings.DEBUG = True

        with self.assertRaises(Person.DoesNotExist):
            p = Person.objects.get(pk=1000)
        self.assertEqual(len(db.connection.queries), 0)

    def test_create(self):
        from django.conf import settings
        from django import db
        settings.DEBUG = True

        p2 = Person(name='Test User 2', ssn='123456788')
        p2.save()

        self.assertEqual(len(db.connection.queries), 1)

        p2_r = Person.objects.get(pk=p2.pk)
        self.assertEqual(p2, p2_r)

        self.assertEqual(len(db.connection.queries), 1)
