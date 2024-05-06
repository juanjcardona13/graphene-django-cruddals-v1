from functools import partial, singledispatch

from cruddals_django.converter.utils import get_django_field_description
from cruddals_django.registry.registry_global import RegistryGlobal
from cruddals_django.types.scalars.Binary import Binary
from cruddals_django.types.scalars.Duration import Duration
from cruddals_django.types.scalars.Email import Email
from cruddals_django.types.scalars.IP import IP
from cruddals_django.types.scalars.IPv4 import IPv4
from cruddals_django.types.scalars.PositiveInt import PositiveInt
from cruddals_django.types.scalars.Slug import Slug
from cruddals_django.types.scalars.URL import URL

from django.db import models
from django.utils.functional import Promise

from graphene import (
    ID,
    UUID,
    Boolean,
    Date,
    DateTime,
    Dynamic,
    Field,
    Float,
    Int,
    List,
    NonNull,
    String,
    Time,
    Decimal,
    JSONString,
    BigInt,
    ObjectType
)


from graphql.pyutils import register_description

from ..copy_graphene_django.compat import ArrayField, HStoreField, JSONField, PGJSONField, RangeField


def get_unbound_function(func):
    if not getattr(func, "__self__", True):
        return func.__func__
    return func


def resolve_for_relation_field(field, model, _type, root, info, **args):
    attname = field.name
    default_value = field.default
    instance = getattr(root, attname, default_value)
    queryset = model.objects.filter(id=instance.id)
    _type.get_queryset(queryset, info)
    return queryset.get()


def get_function_for_type(graphene_type, func_name, name):

    """Gets a resolve function for a given ObjectType"""
    if not issubclass(graphene_type, ObjectType):
        return
    resolver = getattr(graphene_type, func_name, None)
    if not resolver:
        # If we don't find the resolver in the ObjectType class, then try to
        # find it in each of the interfaces
        interface_resolver = None
        for interface in graphene_type._meta.interfaces:
            if name not in interface._meta.fields:
                continue
            interface_resolver = getattr(interface, func_name, None)
            if interface_resolver:
                break
        resolver = interface_resolver

    # Only if is not decorated with classmethod
    if resolver:
        return get_unbound_function(resolver)

@singledispatch
def convert_django_field(field, registry:RegistryGlobal=None):
    raise Exception(
        "Don't know how to convert the Django field {} ({})".format(
            field, field.__class__
        )
    )

@convert_django_field.register(models.BigAutoField)
@convert_django_field.register(models.AutoField)
@convert_django_field.register(models.SmallAutoField)
def convert_field_to_id(field, registry:RegistryGlobal=None):
    return ID(description=get_django_field_description(field), required=not field.blank)


@convert_django_field.register(models.CharField)
@convert_django_field.register(models.TextField)
@convert_django_field.register(models.FilePathField)
@convert_django_field.register(models.FileField)
@convert_django_field.register(models.ImageField)
def convert_field_to_string(field, registry:RegistryGlobal=None):
    return String(
        description=get_django_field_description(field), required=not field.blank
    )


@convert_django_field.register(models.PositiveSmallIntegerField)
@convert_django_field.register(models.SmallIntegerField)
@convert_django_field.register(models.IntegerField)
def convert_field_to_int(field, registry:RegistryGlobal=None):
    return Int(description=get_django_field_description(field), required=not field.blank)


@convert_django_field.register(models.NullBooleanField)
@convert_django_field.register(models.BooleanField)
def convert_field_to_boolean(field, registry:RegistryGlobal=None):
    return Boolean( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.BigIntegerField)
def convert_field_to_big_int(field, registry:RegistryGlobal=None):
    return BigInt(description=field.help_text, required=not field.blank)


@convert_django_field.register(models.DateField)
def convert_field_to_date(field, registry:RegistryGlobal=None):
    return Date( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.TimeField)
def convert_field_to_time(field, registry:RegistryGlobal=None):
    return Time( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.DateTimeField)
def convert_field_to_datetime(field, registry:RegistryGlobal=None):
    return DateTime( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.DecimalField)
def convert_field_to_decimal(field, registry:RegistryGlobal=None):
    return Decimal( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.FloatField)
def convert_field_to_float(field, registry:RegistryGlobal=None):
    return Float( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.DurationField)
def convert_field_to_duration(field, registry:RegistryGlobal=None):
    return Duration( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.BinaryField)
def convert_field_to_binary(field, registry:RegistryGlobal=None):
    return Binary( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(HStoreField)
@convert_django_field.register(PGJSONField)
@convert_django_field.register(JSONField)
def convert_pg_and_json_field_to_json_string(field, registry:RegistryGlobal=None):
    return JSONString( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.UUIDField)
def convert_field_to_uuid(field, registry:RegistryGlobal=None):
    return UUID( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.EmailField)
def convert_field_to_email(field, registry:RegistryGlobal=None):
    return Email( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.GenericIPAddressField)
def convert_field_to_ipv4(field, registry:RegistryGlobal=None):
    return IPv4( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.IPAddressField)
def convert_field_to_ip(field, registry:RegistryGlobal=None):
    return IP( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.PositiveIntegerField)
def convert_field_to_positive_int(field, registry:RegistryGlobal=None):
    return PositiveInt( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.SlugField)
def convert_field_to_slug(field, registry:RegistryGlobal=None):
    return Slug( description=get_django_field_description(field), required=not field.blank )


@convert_django_field.register(models.URLField)
def convert_field_to_url(field, registry:RegistryGlobal=None):
    return URL( description=get_django_field_description(field), required=not field.blank )





@convert_django_field.register(models.OneToOneRel)
def convert_onetoone_field_to_djangomodel(field, registry:RegistryGlobal=None):
    related_model = field.related_model
    direct_model = field.model

    def dynamic_type():
        related_type = None
        direct_type= None
        
        registries_for_related_model = registry.get_registry_for_model(related_model)
        if registries_for_related_model is not None and "object_type" in registries_for_related_model:
            related_type = registries_for_related_model["object_type"]

        registries_for_direct_model = registry.get_registry_for_model(direct_model)
        if registries_for_direct_model is not None and "object_type" in registries_for_direct_model:
            direct_type = registries_for_direct_model["object_type"]


        if not related_type:
            return
        
        default_resolver = partial(resolve_for_relation_field, field, related_model, related_type)

        if direct_type:
            default_resolver = get_function_for_type(direct_type, f"resolve_{field.name}", field.name)

        return Field( related_type, required=not field.null, resolver=default_resolver)

    return Dynamic(dynamic_type)


@convert_django_field.register(models.OneToOneField)
@convert_django_field.register(models.ForeignKey)
def convert_field_to_djangomodel(field, registry:RegistryGlobal=None):
    related_model = field.related_model
    direct_model = field.model

    def dynamic_type():
        related_type = None
        direct_type= None
        
        registries_for_related_model = registry.get_registry_for_model(related_model)
        if registries_for_related_model is not None and "object_type" in registries_for_related_model:
            related_type = registries_for_related_model["object_type"]

        registries_for_direct_model = registry.get_registry_for_model(direct_model)
        if registries_for_direct_model is not None and "object_type" in registries_for_direct_model:
            direct_type = registries_for_direct_model["object_type"]


        if not related_type:
            return
        
        default_resolver = partial(resolve_for_relation_field, field, related_model, related_type)

        if direct_type:
            default_resolver = get_function_for_type(direct_type, f"resolve_{field.name}", field.name)

        return Field( related_type, description=get_django_field_description(field), required=not field.blank, resolver=default_resolver)

    return Dynamic(dynamic_type)


@convert_django_field.register(models.ManyToManyField)
@convert_django_field.register(models.ManyToManyRel)
@convert_django_field.register(models.ManyToOneRel)
def convert_field_to_list_or_connection(field, registry:RegistryGlobal=None):
    model = field.related_model

    def dynamic_type():
        from cruddals_django.copy_graphene_django.fields import DjangoPaginatedField, DjangoListField
        from cruddals_django.utils.utils import get_order_by_arg, get_paginated_arg, get_where_arg
        
        _type = None
        registries_for_model = registry.get_registry_for_model(model)
        if registries_for_model is not None and "object_type" in registries_for_model:
            _type = registries_for_model["object_type"]
        if not _type:
            return
        
        args = { 
            **get_where_arg(model=model),
            **get_order_by_arg(model=model),
            **get_paginated_arg(),
        }

        # if isinstance(field, models.ManyToManyField):
        #     description = get_django_field_description(field)
        # else:
        #     description = get_django_field_description(field.field)
        # return DjangoListField( _type, required=True, description=description, )
        # return Field(type_=paginated_type, args=args)

        return DjangoPaginatedField( _type, args=args)

    return Dynamic(dynamic_type)





@convert_django_field.register(ArrayField)
def convert_postgres_array_to_list(field, registry:RegistryGlobal=None):
    inner_type = convert_django_field(field.base_field)
    if not isinstance(inner_type, (List, NonNull)):
        inner_type = ( NonNull(type(inner_type)) if inner_type.kwargs["required"] else type(inner_type) )
    return List(
        inner_type,
        description=get_django_field_description(field),
        required=not field.blank,
    )

@convert_django_field.register(RangeField)
def convert_postgres_range_to_string(field, registry:RegistryGlobal=None):
    inner_type = convert_django_field(field.base_field)
    if not isinstance(inner_type, (List, NonNull)):
        inner_type = ( NonNull(type(inner_type)) if inner_type.kwargs["required"] else type(inner_type) )
    return List(
        inner_type,
        description=get_django_field_description(field),
        required=not field.blank,
    )


# Register Django lazy()-wrapped values as GraphQL description/help_text.
# This is needed for using lazy translations, see https://github.com/graphql-python/graphql-core-next/issues/58.
register_description(Promise)
