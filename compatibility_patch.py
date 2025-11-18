# Add the missing collections.MutableMapping compatibility for Python 3.10+
# This needs to be imported before any other modules
import collections
import collections.abc

# Fix for older packages that still use collections.MutableMapping
if not hasattr(collections, 'MutableMapping'):
    collections.MutableMapping = collections.abc.MutableMapping

# Ensure other commonly needed ABCs are available in both places
for name in ['Mapping', 'Sequence', 'Iterable', 'Iterator', 'Container']:
    if hasattr(collections.abc, name) and not hasattr(collections, name):
        setattr(collections, name, getattr(collections.abc, name))

print("✅ Applied collections ABC compatibility patch for Python 3.10+")