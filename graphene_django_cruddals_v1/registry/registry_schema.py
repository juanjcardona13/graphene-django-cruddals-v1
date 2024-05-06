class RegistrySchema(object):
    registry_schema = None
    def __init__(self, schema):
        self.registry_schema = schema


registry_schema = None


def set_global_registry_schema(schema):
    global registry_schema
    if not registry_schema:
        registry_schema = RegistrySchema(schema)
        return registry_schema
    else:
        raise RuntimeError('registry_schema already defined.')


def get_global_registry_schema():
    global registry_schema
    if not registry_schema:
        return None
    return registry_schema.registry_schema


def reset_global_registry_schema():
    global registry_schema
    registry_schema = None
