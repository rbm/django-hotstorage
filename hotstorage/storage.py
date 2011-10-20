from django.db import models
from redis import Redis

try:
    import cPickle as pickle
except:
    import pickle

# FIXME: NOPE
redis_client = Redis()


def _build_redis_querystring(**kwargs):
    keys = set(kwargs.keys())
    kv_strings = []
    for key in keys:
        kv_strings.append('%s:%s' % (key, kwargs[key]))
    return ':'.join(kv_strings)


class HotStorageQuerySet(models.query.QuerySet):
    def _is_primary_key(self, field_name):
        if field_name == 'pk':
            return True
        if self.model.get_primary_key_field() == field_name:
            return True
        return False

    def _satisfy_unique_query(self, query_fields):
        if len(query_fields) == 1 and self._is_primary_key(query_fields[0]):
            return True
        if set(query_fields) in self.model.get_unique_constraints():
            return True
        return False

    def _get_object_from_redis(self, **kwargs):
        prefix = self.model.get_key_prefix()

        if len(kwargs) == 1 and self._is_primary_key(kwargs.keys()[0]):
            # Primary key/id lookup, go directly to object storage
            pk_val = kwargs.values()[0]
        else:
            # Other unique constraint lookup, look up primary key
            querystring = _build_redis_querystring(**kwargs)
            pk_val = redis_client.get('%s:%s' % (prefix, querystring))

        if not pk_val:
            # This is why this isn't a cache.
            return None

        # Grab the object from redis by pk and deserialize
        raw_obj = redis_client.get('%s:%s' % (prefix, 'pk:%s' % pk_val))
        if not raw_obj:
            return None
        return pickle.loads(raw_obj)

    def get(self, *args, **kwargs):
        if len(args) > 0:
            # XXX: Does not support get() with Q objects for now--
            # too complicated to introspect
            return super(HotStorageQuerySet, self).get(*args, **kwargs)

        query_fields = kwargs.keys()
        if not self._satisfy_unique_query(query_fields):
            # Not an exact match for a unique constraint, go to database.
            # XXX: Could be extended to support supersets of unique constraints
            # and do additional filtering on object returned (since supersets
            # should return only 1 or 0 results.)
            return super(HotStorageQuerySet, self).get(*args, **kwargs)

        obj = self._get_object_from_redis(**kwargs)
        if obj is None:
            raise self.model.DoesNotExist("%s matching query does not exist." % self.model._meta.object_name)
        return obj


class HotStorageManager(models.Manager):
    def get_query_set(self):
        return HotStorageQuerySet(self.model, using=self._db)


class HotStorageMixin(models.Model):
    objects = HotStorageManager()

    class Meta:
        abstract = True

    @classmethod
    def get_primary_key_field(clazz):
        return clazz._meta.pk.attname

    @classmethod
    def get_unique_constraints(clazz):
        # FIXME: This is hacky, but the most compatible-seeming way of
        # retrieving unique constraints requires a model instance, so...
        inst = clazz()

        constraints = []
        for class_constraints in inst._get_unique_checks():
            for unique_constraint in class_constraints:
                # unique_constraint is a tuple(className, tuple(field_list))
                if len(unique_constraint[1]) == 1:
                    # One-field unique constraint-- is this the primary key?
                    if unique_constraint[1][0] == clazz.get_primary_key_field():
                        # Yep, handled by primary storage
                        continue
                constraints.append(set(unique_constraint[1]))
        return constraints

    @classmethod
    def get_key_prefix(clazz):
        return '%s.%s' % (clazz.__module__.lower(), clazz.__name__.lower())

    def _get_primary_redis_key(self):
        return '%s:pk:%s' % (self.get_key_prefix(), self.pk)
    redis_pk = property(_get_primary_redis_key)

    def _get_unique_redis_keys(self):
        keys = []
        for constraint in self.__class__.get_unique_constraints():
            keyvalues = dict([(name, self.__dict__.get(name)) for name in constraint])
            querystring = _build_redis_querystring(**keyvalues)
            keys.append('%s:%s' % (self.__class__.get_key_prefix(), querystring))
        return keys
    redis_unique_keys = property(_get_unique_redis_keys)

    def _dump(self):
        return pickle.dumps(self)

    def _save_to_redis(self):
        redis_client.set(self.redis_pk, self._dump())
        redis_client.sadd('%s:all' % self.get_key_prefix(), self.pk)

        index_list_key = '%s:indexes' % self.redis_pk
        existing_indexes = redis_client.smembers(index_list_key) or []

        unique_keys = self.redis_unique_keys
        # If indexes are the same, we're done
        if existing_indexes != unique_keys:
            # We've changed a unique key on this object (or it's new)
            for unique_key in unique_keys:
                # Set each unique key and ensure it's in the index list
                redis_client.set(unique_key, self.pk)
                if unique_key in existing_indexes:
                    existing_indexes.remove(unique_key)
                else:
                    redis_client.sadd(index_list_key, unique_key)
            for invalidated_index in existing_indexes:
                # Anything left in existing_indexes is no longer valid, so
                # remove and delete from the index list
                redis_client.delete(invalidated_index)
                redis_client.srem(index_list_key, invalidated_index)

    def save(self, **kwargs):
        super(HotStorageMixin, self).save(**kwargs)
        # No exception, so save to Redis
        self._save_to_redis()

    def _delete_from_redis(self):
        redis_client.delete(self.redis_pk)
        redis_client.srem('%s:all' % self.get_key_prefix(), self.pk)

        index_list_key = '%s:indexes' % self.redis_pk
        existing_indexes = redis_client.smembers(index_list_key) or []
        for invalidated_index in existing_indexes:
            redis_client.delete(invalidated_index)
        redis_client.delete(index_list_key)

    def delete(self, **kwargs):
        self._delete_from_redis()
        super(HotStorageMixin, self).delete(**kwargs)

