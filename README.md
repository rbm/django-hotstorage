# Hey you

You almost certainly don't want use this. It's never been run in production and I have no plans to work on it further. It was an idea to compensate for some issues in with a particular use case for Django that ended up being best solved by taking Django out of the equation.

If you're writing a fine-grained caching layer for Django, this may be useful to gather some ideas from. You'd want to handle batch update() and delete() on QuerySets (Hearsay Social avoids those operations for other reasons, so I never bothered trying to implement them here.)

--

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
