from collections import OrderedDict
from enum import Enum
from functools import singledispatch
from cruddals_django.converter.utils import get_django_field_description


from cruddals_django.registry.registry_global import RegistryGlobal
from cruddals_django.types.scalars.Binary import Binary
from cruddals_django.types.scalars.OrderEnum import OrderEnum
from cruddals_django.types.scalars.Upload import Upload
from cruddals_django.types.scalars.Duration import Duration
from cruddals_django.types.scalars.Email import Email
from cruddals_django.types.scalars.IP import IP
from cruddals_django.types.scalars.IPv4 import IPv4
from cruddals_django.types.scalars.PositiveInt import PositiveInt
from cruddals_django.types.scalars.Slug import Slug
from cruddals_django.types.scalars.URL import URL

from django.db import models
from django.db.models.fields import Field as DjangoField
from django.utils.functional import Promise

import graphene
from graphene import (
    ID,
    UUID,
    Boolean,
    Date,
    DateTime,
    Dynamic,
    Float,
    Int,
    List,
    String,
    Time,
    Decimal,
    JSONString,
    BigInt
)


from graphql.pyutils import register_description

from ..copy_graphene_django.compat import ArrayField, HStoreField, JSONField, PGJSONField, RangeField


class TypesOfInput(Enum):
    FOR_MUTATE = "for_mutate"
    """input_fields are InputField"""
    FOR_SEARCH = "for_search"
    """input_fields are FiltersInputField"""
    FOR_ORDER_BY = "for_order_by"
    """Input_fields are OrderInputField"""


def get_filter_input_object_type(django_field:DjangoField, type_of_field, name:str):
    from cruddals_django.utils.utils import build_class
    input_fields = OrderedDict()
    lookups = django_field.get_lookups()
    for name_lookup, lookup in lookups.items():
        if name_lookup == "regex" or name_lookup == "iregex":
            input_fields[name_lookup] = graphene.InputField(type_=graphene.String)
        elif name_lookup == "in":
            input_fields[name_lookup] = graphene.InputField(type_=graphene.List(of_type=type_of_field))
        elif name_lookup == "isnull":
            input_fields[name_lookup] = graphene.InputField(type_=graphene.Boolean) 
        else:
            input_fields[name_lookup] = graphene.InputField(type_=type_of_field)
    
    return build_class(
        name=name,
        bases=(graphene.InputObjectType,),
        attrs=input_fields
    )


@singledispatch
def convert_django_field_to_input(field:DjangoField, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    raise Exception(
        "Don't know how to convert the Django field {} ({})".format(
            field, field.__class__
        )
    )

@convert_django_field_to_input.register(models.BigAutoField)
@convert_django_field_to_input.register(models.AutoField)
@convert_django_field_to_input.register(models.SmallAutoField)
def convert_field_to_id(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, ID, "IDFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return


@convert_django_field_to_input.register(models.CharField)
@convert_django_field_to_input.register(models.TextField)
@convert_django_field_to_input.register(models.FilePathField)
def convert_field_to_string(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, String, "StringFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return String( description=get_django_field_description(field), required=not field.blank )



@convert_django_field_to_input.register(models.FileField)
@convert_django_field_to_input.register(models.ImageField)
def convert_field_to_upload_or_string(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, String, "StringFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Upload( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.PositiveSmallIntegerField)
@convert_django_field_to_input.register(models.SmallIntegerField)
@convert_django_field_to_input.register(models.IntegerField)
def convert_field_to_int(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Int, "IntFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Int(description=get_django_field_description(field), required=not field.blank)


@convert_django_field_to_input.register(models.NullBooleanField)
@convert_django_field_to_input.register(models.BooleanField)
def convert_field_to_boolean(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Boolean, "BooleanFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Boolean( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.BigIntegerField)
def convert_field_to_big_int(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, BigInt, "BigIntFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return BigInt(description=field.help_text, required=not field.blank)


@convert_django_field_to_input.register(models.DateField)
def convert_field_to_date(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Date, "DateFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Date( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.TimeField)
def convert_field_to_time(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Time, "TimeFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Time( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.DateTimeField)
def convert_field_to_datetime(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, DateTime, "DateTimeFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return DateTime( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.DecimalField)
def convert_field_to_decimal(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Decimal, "DecimalFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Decimal( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.FloatField)
def convert_field_to_float(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Float, "FloatFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Float( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.DurationField)
def convert_field_to_duration(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Duration, "DurationFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Duration( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.BinaryField)
def convert_field_to_binary(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        #TODO: Revisar por que en gdc no lo devuelve
        _input_object_type = get_filter_input_object_type(field, Binary, "BinaryFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        pass
    else: # FOR_MUTATE
        return Binary( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(HStoreField)
@convert_django_field_to_input.register(PGJSONField)
@convert_django_field_to_input.register(JSONField)
def convert_pg_and_json_field_to_json_string(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, JSONString, "JSONStringFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        pass
    else: # FOR_MUTATE
        return JSONString( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.UUIDField)
def convert_field_to_uuid(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, UUID, "UUIDFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return UUID( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.EmailField)
def convert_field_to_email(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Email, "EmailFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Email( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.GenericIPAddressField)
def convert_field_to_ipv4(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, IPv4, "IPv4Filter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return IPv4( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.IPAddressField)
def convert_field_to_ip(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, IP, "IPFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return IP( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.PositiveIntegerField)
def convert_field_to_positive_int(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, PositiveInt, "PositiveIntFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return PositiveInt( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.SlugField)
def convert_field_to_slug(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, Slug, "SlugFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return Slug( description=get_django_field_description(field), required=not field.blank )


@convert_django_field_to_input.register(models.URLField)
def convert_field_to_url(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    if type_input == TypesOfInput.FOR_SEARCH.value:
        _input_object_type = get_filter_input_object_type(field, URL, "URLFilter")
        return _input_object_type(description=get_django_field_description(field))
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return OrderEnum()
    else: # FOR_MUTATE
        return URL( description=get_django_field_description(field), required=not field.blank )





@convert_django_field_to_input.register(models.OneToOneRel)
def convert_onetoone_field_to_djangomodel(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    model = field.related_model
    if type_input == TypesOfInput.FOR_MUTATE.value:
        from cruddals_django.utils.utils import converter_pk_field
        pk_field = model._meta.pk
        converted_pk_field = converter_pk_field(pk_field, registry, type_input)
        if not converted_pk_field:
            return ID(required=not field.null)
        converted_pk_field.kwargs.update({"required": not field.null})
        return converted_pk_field
    else:
        
        def dynamic_type():
            registries_for_model = registry.get_registry_for_model(model)
            if registries_for_model is None:
                return
            if type_input == TypesOfInput.FOR_SEARCH.value:
                from cruddals_django.utils.utils import convert_model_to_filter_input_object_type
                return graphene.InputField( convert_model_to_filter_input_object_type( model ) )
            elif type_input == TypesOfInput.FOR_ORDER_BY.value:
                from cruddals_django.utils.utils import convert_model_to_order_by_input_object_type
                return graphene.InputField( convert_model_to_order_by_input_object_type( model ) )
        return Dynamic(dynamic_type)


@convert_django_field_to_input.register(models.ManyToManyField)
@convert_django_field_to_input.register(models.ManyToManyRel)
@convert_django_field_to_input.register(models.ManyToOneRel)
def convert_field_to_list_or_connection(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    model = field.related_model
    if type_input == TypesOfInput.FOR_MUTATE.value:
        from cruddals_django.utils.utils import converter_pk_field
        pk_field = model._meta.pk
        converted_pk_field = converter_pk_field(pk_field, registry, type_input)
        if not converted_pk_field:
            return List(ID, required=not field.blank)
        return List(converted_pk_field.__class__, required=not field.blank)
    elif type_input == TypesOfInput.FOR_ORDER_BY.value:
        return
    else:
        
        def dynamic_type():
            registries_for_model = registry.get_registry_for_model(model)
            if registries_for_model is None:
                return
            if type_input == TypesOfInput.FOR_SEARCH.value:
                from cruddals_django.utils.utils import convert_model_to_filter_input_object_type
                return graphene.InputField( convert_model_to_filter_input_object_type( model ) )    
        return Dynamic(dynamic_type)


@convert_django_field_to_input.register(models.OneToOneField)
@convert_django_field_to_input.register(models.ForeignKey)
def convert_field_to_djangomodel(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
    model = field.related_model
    if type_input == TypesOfInput.FOR_MUTATE.value:
        from cruddals_django.utils.utils import converter_pk_field
        pk_field = model._meta.pk
        converted_pk_field = converter_pk_field(pk_field, registry, type_input)
        if not converted_pk_field:
            return ID(required=not field.blank)
        converted_pk_field.kwargs.update({"required": not field.blank})
        return converted_pk_field
    else:
        
        def dynamic_type():
            registries_for_model = registry.get_registry_for_model(model)
            if registries_for_model is None:
                return
            # Avoid create field for auto generate OneToOneField product of an inheritance
            if isinstance(field, models.OneToOneField) and issubclass( field.model, field.related_model ):
                return
            if type_input == TypesOfInput.FOR_SEARCH.value:
                from cruddals_django.utils.utils import convert_model_to_filter_input_object_type
                return graphene.InputField( convert_model_to_filter_input_object_type( model ) )
            elif type_input == TypesOfInput.FOR_ORDER_BY.value:
                from cruddals_django.utils.utils import convert_model_to_order_by_input_object_type
                return graphene.InputField( convert_model_to_order_by_input_object_type( model ) )
        return Dynamic(dynamic_type)





"""TODO"""
# @convert_django_field_to_input.register(ArrayField)
# def convert_postgres_array_to_list(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
#     if type_input == TypesOfInput.FOR_SEARCH.value:
#         pass
#     else: # FOR_MUTATE

#         inner_type = convert_django_field_to_input(field.base_field)
#         if not isinstance(inner_type, (List, NonNull)):
#             inner_type = (
#                 NonNull(type(inner_type))
#                 if inner_type.kwargs["required"]
#                 else type(inner_type)
#             )
#         return List(
#             inner_type,
#             description=get_django_field_description(field),
#             required=not field.blank,
#         )

# @convert_django_field_to_input.register(RangeField)
# def convert_postgres_range_to_string(field, registry:RegistryGlobal=None, type_input:TypesOfInput="for_mutate"):
#     if type_input == TypesOfInput.FOR_SEARCH.value:
#         pass
#     else: # FOR_MUTATE

#         inner_type = convert_django_field_to_input(field.base_field)
#         if not isinstance(inner_type, (List, NonNull)):
#             inner_type = (
#                 NonNull(type(inner_type))
#                 if inner_type.kwargs["required"]
#                 else type(inner_type)
#             )
#         return List(
#             inner_type,
#             description=get_django_field_description(field),
#             required=not field.blank,
#         )


# Register Django lazy()-wrapped values as GraphQL description/help_text.
# This is needed for using lazy translations, see https://github.com/graphql-python/graphql-core-next/issues/58.
register_description(Promise)
