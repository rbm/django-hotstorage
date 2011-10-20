django-hotstorage: Secondary storage for Django models in Redis, indexed by primary and natural keys

# Redis Storage Structure

## Object Storage: (Redis scalar, pickled object)
     modulename.modelname:pk:pk_value

## Single-field unique indexes (Redis scalar, primary key reference)
     modulename.modelname:uniquefieldname:uniquefieldvalue

## Multiple-field unique indexes (Redis scalar, primary key reference)
     modulename.modelname:uniquefieldname1:val1:uniquefieldname2:val2

## All primary keys for model (Redis set, list of PKs)
    modulename.modelname:all

## List of indexes for object (Redis set, list of Redis keys)
    modulename.modelname:pk:pk_value:indexes


# Operations

## Retrieving objects (Model.objects.get)

If a get() operation is performed on a model inheriting from HotStorageMixin that is sufficiently simple (no Q/complex
lookups, examples: Model.objects.get(pk=ID), Model.objects.get(name='Name', phone='Phone Number')) and the key requested
satisfies a unique constraint (any primary key, unique field or conjunction of fields that make up a unique constraint),
hotstorage will bypass the database and retrieve the object from Redis.

If the query is a primary key lookup, Redis will retrieve the object
directly (one Redis operation.) If it's a index/unique constraint lookup,
hotstorage will look up the appropriate key to determine the primary key of
the object and then retrieve the object from there (two Redis operations.)

filter() operations are unsupported at this time.

Futures: Support queries that are supersets of a unique constraint and do
filtering in the application.

## Storing objects (Model.save())

Upon saving an object, hotstorage will first save it to the database as
usual, determining the primary key if the object is new. It will then
serialize the object and save it under the appropriate primary storage key
in Redis and then append the primary key to the 'all' set in Redis.

hotstorage will then retrieve the list of indexes for the object from
'module.model.pk:pk_value.indexes'. If the list of indexes computed from
the current object is the same as the list retrieved from Redis, hotstorage
will return. Otherwise, hotstorage will traverse the computed index list
and store the primary key in a corresponding key for each index, also
appending the index key to the existing list in Redis.

Any indexes in the existing list from Redis not present in the computed
list will then be removed from the Redis set, thus invalidating stale indexes.

## Deleting objects (Model.delete())

Before deleting an object from the database, hotstorage will:

* Delete the primary storage key for the object.
* Remove the object's primary key from the 'all' set for the model.
* Retrieve the existing index list for the object from Redis.
* Traverse the existing index list and delete each key from Redis.
* Delete the existing index list.

# Caveats

* hotstorage is not SQL transaction-safe.
* Foreign key handling may do unexpected things.

# Futures

## Deferred Mode

hotstorage should eventually implement a deferred mode, wherein writes are
sent only to Redis, to be synced to the database asynchronously later.

The storage structure might look like this:

### Dirty working set (Redis set, list of primary keys that have yet to be saved to database)
     modulename.modelname:dirty

### Unsaved new object storage (Redis scalar, pickled object)
    modulename.modelname:new:uuid

### Created indexes (Redis set, list of UUIDs)
    appname.modulename.modelname:new:all
    appname.modulename.modelname:new:uniquefieldname:val
    appname.modulename.modelname:new:uniquefieldname:val1:uniquefieldname2:val2

This mode may be very unsafe; it will be up to the application to ensure
sync is possible, and the sync logic itself should be handled by the
application. In the best case, writes should only come from
the deferred-enabled processing, ensuring consistency.

## Redis-only/SQL-only fields

hotstorage should eventually support marking certain model fields for
storage only in the database or in Redis, so that e.g. very volatile fields
or summary data can be stored purely in Redis and avoid database write
load, and that rarely-used space-intensive fields may be stored only in the
database, avoiding Redis memory bloat.
