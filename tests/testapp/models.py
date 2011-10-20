from django.db import models
from hotstorage import HotStorageMixin

class Person(HotStorageMixin):
    name = models.CharField(max_length=256)
    ssn = models.CharField(max_length=9, unique=True)

class PhoneNumber(HotStorageMixin):
    person = models.ForeignKey(Person)
    label = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=4)

    class Meta:
        unique_together = (('person', 'phone_number'))
