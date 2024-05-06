# -*- coding: utf-8 -*-

from enum import Enum
import operator
import importlib
import sys
import re
import warnings

from collections import OrderedDict
from typing import Dict
from django.db.models.functions import Lower

import graphene
from graphene.types.utils import yank_fields_from_attrs

from django.forms.models import model_to_dict
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.forms import ModelForm as DjangoModelForm

from graphql import GraphQLError

from functools import reduce
from cruddals_django.converter.utils import FieldPurposeConvert, convert_django_field_with_choices
from cruddals_django.copy_graphene_django.types import ErrorType, ErrorsType
from cruddals_django.registry.registry_global import RegistryGlobal, TypeRegistryForField, get_global_registry
from ..helpers.helpers import CruddalsRelationField, PaginatedInput, PaginationInterface, TypesMutation

from collections.abc import Iterable

import inspect
from django import VERSION as DJANGO_VERSION
from django.db import connection, models, transaction
from django.db.models.manager import Manager
from itertools import chain
from django.db.models import (
    NOT_PROVIDED,
    Q,
    QuerySet,
    Model as DjangoModel,
    AutoField,
    BigAutoField,
    SmallAutoField,
    ManyToOneRel,
    ManyToManyRel,
    OneToOneRel,
    ManyToManyField,
    ForeignKey, 
    OneToOneField,
    FileField,
    ImageField,
    Field as DjangoField
)
from django.utils.encoding import force_str
from django.utils.functional import Promise
from django.utils.datastructures import MultiValueDict

from graphene.utils.str_converters import to_camel_case

import re
from text_unidecode import unidecode

from graphene.types.mutation import MutationOptions
from cruddals_django.copy_graphene_django.constants import MUTATION_ERRORS_FLAG
from django.core.exceptions import ValidationError


class TypePurposeInputFields(Enum):
    MUTATE = "mutate"
    FILTER = "filter"
    ORDER_BY = "order_by"


def to_const(string):
    return re.sub(r"[\W|^]+", "_", unidecode(string)).upper()

def is_iterable(obj, exclude_string=True):
    if exclude_string:
        return isinstance(obj, Iterable) and not isinstance(obj, str)
    return isinstance(obj, Iterable)

def _camelize_django_str(s):
    if isinstance(s, Promise):
        s = force_str(s)
    return to_camel_case(s) if isinstance(s, str) else s

def camelize(data):
    if isinstance(data, dict):
        return {_camelize_django_str(k): camelize(v) for k, v in data.items()}
    if is_iterable(data) and not isinstance(data, (str, Promise)):
        return [camelize(d) for d in data]
    return data

def is_included(name, only_fields, exclude_fields):
    return only_fields == "__all__" and name not in exclude_fields or name in only_fields

def get_reverse_fields(model: DjangoModel):
    reverse_fields = { field.name: field for field in model._meta.get_fields() if field.auto_created and not field.concrete }

    for name, field in reverse_fields.items():
        # Django =>1.9 uses 'rel', django <1.9 uses 'related'
        related = getattr(field, "rel", None) or getattr(field, "related", None)
        if isinstance(related, ManyToOneRel) or (isinstance(related, ManyToManyRel) and not related.symmetrical):
            yield name, related

def get_field_name(field, for_queryset):
    # Si el campo es un tipo de relación y se está consultando para un queryset,
    # se usa el nombre de la consulta relacionada si está disponible.
    if for_queryset and isinstance(field, (OneToOneRel, ManyToManyRel, ManyToOneRel)) and field.related_query_name is not None:
        return field.related_query_name

    # Si el campo es una relación ManyToMany o ManyToOne, y no se está consultando para un queryset,
    # se usa el nombre relacionado si está disponible, de lo contrario, se usa el nombre de accessor.
    if not for_queryset and isinstance(field, (ManyToManyRel, ManyToOneRel)) and field.related_name is not None:
        return field.related_name
    elif not for_queryset and isinstance(field, (ManyToManyRel, ManyToOneRel)):
        n = field.get_accessor_name()
        return n

    # En todos los demás casos, se usa el nombre del campo.
    return field.name

def get_model_fields(model: DjangoModel, for_queryset=False, for_mutation=False, only_fields="__all__", exclude_fields=()):

    # print(model)
    
    if for_mutation:
        sortable_private_fields = [f for f in model._meta.private_fields if isinstance(f, DjangoField)]
        all_fields_list = list(chain(model._meta.concrete_fields, sortable_private_fields, model._meta.many_to_many))
        all_fields_list = [field for field in all_fields_list if getattr(field, 'editable', True) and not isinstance(field, (AutoField, BigAutoField, SmallAutoField))]
    else:
        all_fields_list = list(model._meta.fields) + list(model._meta.many_to_many) + list(model._meta.private_fields) + list(model._meta.fields_map.values())

    reverse_fields = list(get_reverse_fields(model))
    invalid_fields = [field[1] for field in reverse_fields]
    local_fields = [(get_field_name(field, for_queryset), field) for field in all_fields_list if field not in invalid_fields]
    
    all_fields = local_fields + reverse_fields

    return [(name, field) for name, field in all_fields if not str(name).endswith("+") and is_included(name, only_fields, exclude_fields)]

def maybe_queryset(value):
    if isinstance(value, Manager):
        value = value.get_queryset()
    return value

def is_valid_django_model(model):
    return inspect.isclass(model) and issubclass(model, models.Model)

def set_rollback():
    atomic_requests = connection.settings_dict.get("ATOMIC_REQUESTS", False)
    if atomic_requests and connection.in_atomic_block:
        transaction.set_rollback(True)

def validate_list_func_cruddals(functions, exclude_functions):
    valid_values = ["create", "read", "update", "delete", "deactivate", "activate", "list", "search"]

    if functions and exclude_functions:
        raise ValueError("You cannot provide both 'functions' and 'exclude_functions'. Please provide only one.")
    else:
        if functions:
            name_input = "functions"
            input_list = functions
        elif exclude_functions:
            name_input = "exclude_functions" 
            input_list = exclude_functions
        else:
            return True

    if not isinstance(input_list, list) or len(input_list) == 0:
        raise ValueError(f"'{name_input}' must be a non-empty list.")

    invalid_values = [value for value in input_list if value not in valid_values]

    if invalid_values:
        raise ValueError(f"Expected in '{name_input}' a list with some of these values {valid_values}, but got these invalid values {invalid_values}")

    return True

def django_is_running_with_runserver():
    return len(sys.argv) > 1 and sys.argv[1] == 'runserver'

def get_python_obj_from_string(class_path):
    if not isinstance(class_path, str):
        raise TypeError(f"class_path '{class_path}' should be a string representing the full Python import path")
    
    parts = class_path.split('.')
    module_path = '.'.join(parts[:-1])
    class_name = parts[-1]
    module = importlib.import_module(module_path)
    obj = getattr(module, class_name)

    ## Verificar que sea una clase
    # if not inspect.isclass(obj):
    #     raise TypeError(f"{class_path} no es una clase")
    ## Verificar que el objeto pertenezca al módulo
    # if inspect.getmodule(obj) != module:
    #     raise ValueError(f"{class_path} is not a valid module object {module_path}")

    return obj

def check_user_has_permission(permiso, user, Model=None):
    """
    Checks if a user has the specified permission for a given Django model.

    Args:
        permiso (str): The permission to check, should be one of ["add", "change", "read", "enable", "disable", "delete"].
        user (User): The user for which the permission check is performed.
        Model (Model, optional): Django model class. If not provided, the 'cls' parameter must be used.

    Raises:
        GraphQLError: If the user does not have the required permission.
    """
    assert permiso.lower() in ["add", "change", "read", "enable", "disable", "delete"], 'The "permiso" parameter should be one of ["add", "change", "read", "enable", "disable", "delete"]'
    perm = '%s.%s_%s' % (Model._meta.app_label, permiso, Model._meta.model_name)
    if not user.has_perm(perm):
        raise GraphQLError(f"The '{perm}' permission is required for this action")
    
def update_dict_with_model_instance(obj_to_update, instance=None, model=None):
    """
    Updates a dictionary with the values from a Django model instance, based on the provided ID.
    
    Args:
        obj_to_update (dict): Dictionary containing an 'id' key to match the model instance.
        instance (Model, optional): Django model class. If not provided, the 'model' parameter must be used.
        model (Model, optional): Django model instance. If not provided, the 'instance' parameter must be used.
        
    Returns:
        dict: Updated dictionary with the model instance's values.
    """
    if 'id' in obj_to_update:
        if instance is not None:
            obj = instance._meta.model.objects.get(pk=obj_to_update['id'])
        else:
            obj = model.objects.get(pk=obj_to_update['id'])
        obj_original = model_to_dict(obj)
        for name_field, value_field in obj_original.items():
            if name_field not in obj_to_update:
                obj_to_update.update({name_field: value_field})
                setattr(obj_to_update, name_field, value_field)
    return obj_to_update

def toggle_active_status(option, data, field="is_active"):
    """
    Activates or deactivates the state of the model instances based on the provided option.
    
    Args:
        option (str): Action to perform, 'ACTIVATE' or 'DEACTIVATE'.
        data (QuerySet): Data set to modify.
        ids (list): List of IDs to modify.
        field (str, optional): Field to update. By default, it is 'is_active'.
        
    Returns:
        QuerySet: Updated data.
    """
    if option.upper() == 'ACTIVATE':
        data.update(**{field: True})
    elif option.upper() == 'DEACTIVATE':
        data.update(**{field: False})
    return data

def paginate_queryset(qs, page_size="All", page=1, paginated_type=None, **kwargs):
    """
    Paginate a queryset based on the specified parameters.

    :param qs: The queryset to paginate.
    :param page_size: The number of items per page.
    :param page: The current page number.
    :param paginated_type: The pagination type to return.
    :param kwargs: Additional keyword arguments for the paginated_type.
    :return: An instance of paginated_type with pagination information and objects.
    """

    if page_size == 'All':
        page_size = qs.count()
    
    try:
        page = int(page)
        page_size = int(page_size)
    except:
        page = 1
        page_size = 1

    if page == 0:
        page = 1
    if page_size == 0:
        page_size = 1
    
    p = Paginator(qs, page_size)
    
    try:
        page_obj = p.page(page)
    except PageNotAnInteger:
        page_obj = p.page(1)
    except EmptyPage:
        page_obj = p.page(p.num_pages)
    
    return paginated_type(
        total=p.count,
        page=page_obj.number,
        pages=p.num_pages,
        has_next=page_obj.has_next(),
        has_prev=page_obj.has_previous(),
        index_start_obj = page_obj.start_index(),
        index_end_obj = page_obj.end_index(),
        objects=page_obj.object_list,
        **kwargs
    )

def camel_to_snake(s):
    s = str(s)
    s = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', s)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s).lower()

def snake_to_case(s):
    s = str(s)
    return ''.join(word.title() for word in s.split('_'))

def transform_string(s, type):
    """Type: PascalCase, camelCase, snake_case, kebab-case, lowercase"""
    s = str(s)
    if ' ' in s:
        if type == 'PascalCase':
            return ''.join(word.title() for word in s.split(' '))
        elif type == 'snake_case':
            return '_'.join(word.lower() for word in s.split(' '))
        elif type == 'kebab-case':
            return '-'.join(word.lower() for word in s.split(' '))
        elif type == 'lowercase':
            return ''.join(word.lower() for word in s.split(' '))
        else:
            return ''.join(word for word in s.split(' '))
    else:
        if type == 'PascalCase':
            if s[0] == s.title()[0]:
                return s
            else:
                return s.title()
        elif type == 'lowercase':
            return s.lower()

def delete_keys(obj, keys):
    for key in keys:
        if key in obj:
            del obj[key]
    return obj

def merge_dict(source, destination, overwrite=False, keep_both=False, path=None):
    "merges source into destination"
    import copy
    new_destination = copy.deepcopy(destination)

    if path is None: path = []
    for key in source:
        if key in new_destination:
            if isinstance(new_destination[key], dict) and isinstance(source[key], dict):
                new_destination[key] = merge_dict(source[key], new_destination[key], overwrite, keep_both, path + [str(key)])
            elif new_destination[key] == source[key]:
                pass
            else:
                if keep_both:
                    if isinstance(new_destination[key], (list, tuple, set,)) and isinstance(source[key], (list, tuple, set,)):
                        new_destination[key] = new_destination[key] + source[key]
                    else:
                        new_destination[key] = [new_destination[key], source[key]]
                elif overwrite:
                    """Debo de conservar lo que tiene new_destination"""
                    continue
                else:
                    raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            new_destination[key] = source[key]
    return new_destination

def build_class(name, bases=(), attrs={}):
    return type(name, bases, attrs)

def get_class_in_bases(cls, name):
    class_base = None
    bases = cls.__bases__
    for base in bases:
        if base.__name__ == name:
            class_base = base
            break
    return class_base

def add_cruddals_model_to_request(info, cruddals_model):
    try:
        if info.context is None:
            class Context:
                pass
            setattr(info, 'context', Context())
        setattr(info.context, 'CruddalsModel', cruddals_model)
    except Exception as e:
        pass

def get_name_of_model_in_different_case(model, prefix="", suffix=""):

    # snake_case
    # kebab-case
    # camelCase
    # PascalCase

    prefix_lower = prefix.lower()
    prefix_capitalize = prefix.capitalize()

    suffix_lower = suffix.lower()
    suffix_capitalize = suffix.capitalize()

    name_model = model.__name__
    name_model_plural = transform_string(model._meta.verbose_name_plural, "PascalCase")


    snake_case = f"{prefix_lower}{'_' if prefix else ''}{camel_to_snake(name_model)}{'_' if suffix else ''}{suffix_lower}"
    plural_snake_case = f"{prefix}{'_' if prefix else ''}{camel_to_snake(transform_string(name_model_plural, 'PascalCase'))}{'_' if suffix else ''}{suffix}"
    
    camel_case = f"{prefix_capitalize}{name_model}{suffix_capitalize}"
    plural_camel_case = f"{prefix_lower}{name_model_plural}{suffix_capitalize}"

    pascal_case = f"{prefix_capitalize}{transform_string(name_model, 'PascalCase')}{suffix_capitalize}"
    plural_pascal_case = f"{prefix}{transform_string(name_model_plural, 'PascalCase')}{suffix}"

    return {
        "snake_case": snake_case,
        "plural_snake_case": plural_snake_case,
        "camel_case": camel_case,
        "plural_camel_case": plural_camel_case,
        "pascal_case": pascal_case,
        "plural_pascal_case": plural_pascal_case,
    }

def convert_model_to_paginated_object_type(model, model_as_object_type=None, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    from cruddals_django.copy_graphene_django.fields import DjangoListField
    
    paginated_model_object_type = None
    registry = get_global_registry(f"{prefix_for_name}{suffix_for_name}")
    registries_for_model = registry.get_registry_for_model(model)
    if registries_for_model is not None and "paginated_object_type" in registries_for_model:
        paginated_model_object_type = registries_for_model["paginated_object_type"]
    if paginated_model_object_type is None:
        if model_as_object_type is None:
            model_as_object_type = convert_model_to_object_type(model=model, prefix_for_name=prefix_for_name, suffix_for_name=suffix_for_name)
        names_of_model = get_name_of_model_in_different_case(model, prefix=prefix_for_name, suffix=suffix_for_name)
        singular_camel_case_name = names_of_model.get("camel_case")
        MetaPaginatedType = build_class(
            name='Meta',
            attrs={
                "interfaces": (PaginationInterface,), 
                "name": f"{singular_camel_case_name}PaginatedType"
            }
        )
        ModelPaginatedType = build_class(
            name=f"{singular_camel_case_name}PaginatedType",
            bases=(graphene.ObjectType,),
            attrs={
                "Meta": MetaPaginatedType, 
                "objects": DjangoListField(model_as_object_type),
                **extra_attrs
            }
        ) 
        registry.register_model(model, "paginated_object_type", ModelPaginatedType)
        return ModelPaginatedType
    else:
        return paginated_model_object_type

def convert_model_to_model_form(model, extra_meta_attrs={}, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    """
        Los extra_meta_attrs que espera recibir son los que permite Django Model Form en su clase interna `Meta`
        la doc encuentran en: https://docs.djangoproject.com/en/4.2/topics/forms/modelforms/#modelform
        y son: 
            "model"
            "fields"
            "exclude"
            "widgets"
            "localized_fields"
            "labels"
            "help_texts"
            "error_messages"
            "field_classes"

        Los extra_attrs que espera recibir son los que permite Django Model Form
        la doc encuentran en: https://docs.djangoproject.com/en/4.2/topics/forms/modelforms/#modelform
        y son:
            TODO: Me falta aprender mas acerca de los forms de Django
    """
    names_of_model = get_name_of_model_in_different_case(model, prefix=prefix_for_name, suffix=suffix_for_name)
    singular_camel_case_name = names_of_model.get("camel_case")

    MetaForm = build_class(
        name="Meta",
        attrs={
            "model": model, 
            "fields": "__all__", 
            "name": f"{singular_camel_case_name}Form", 
            **extra_meta_attrs
        }
    )
    ModelForm = build_class(
        name=f"{singular_camel_case_name}Form",
        bases=(DjangoModelForm,),
        attrs={
            "Meta": MetaForm,
            **extra_attrs
        }
    )
    return ModelForm

def convert_model_to_object_type(model, extra_meta_attrs={}, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    """
        Los extra_meta_attrs que espera recibir son los que permite Django Object Type en su clase interna `Meta`
        la doc encuentran en: https://docs.graphene-python.org/projects/django/en/latest/queries/
        y son: 
            "model"
            "registry"
            "skip_registry"
            "fields"
            "exclude"
            "filter_fields"
            "filterset_class"
            "connection"
            "connection_class"
            "use_connection"
            "interfaces"
            "convert_choices_to_enum"
            "_meta"
            **options

        Los extra_attrs que espera recibir son los que permite Django Object Type los cuales son para custom types con sus resolves
        la doc encuentran en: https://docs.graphene-python.org/projects/django/en/latest/queries/#customising-fields
        y son:
            cualquier atributo con un valor valido de tipo graphene y su función resolve
    """
    from cruddals_django.copy_graphene_django.types import DjangoObjectType

    model_object_type = None
    registry = get_global_registry(f"{prefix_for_name}{suffix_for_name}")
    registries_for_model = registry.get_registry_for_model(model)
    if registries_for_model is not None and "object_type" in registries_for_model:
        model_object_type = registries_for_model["object_type"]
        
    if model_object_type is None:
        names_of_model = get_name_of_model_in_different_case(model, prefix=prefix_for_name, suffix=suffix_for_name)
        singular_camel_case_name = names_of_model.get("camel_case")

        MetaType = build_class(
            name='Meta',
            attrs={
                "model": model,
                "name": f"{singular_camel_case_name}Type",
                "registry": registry,
                **extra_meta_attrs
            }
        )
        ModelObjectType = build_class(
            name=f"{singular_camel_case_name}ObjectType",
            bases=(DjangoObjectType,),
            attrs={
                "Meta": MetaType,
                **extra_attrs
            }
        )  
        return ModelObjectType
    else:
        return model_object_type

def converter_pk_field(pk_field, registry, type_input):
    from cruddals_django.converter.converter_input import convert_django_field_to_input
    return convert_django_field_to_input(pk_field, registry, type_input)

def get_type_and_name_input(purpose, type_mutation, singular_camel_case_name):
    input_type_map = {
        "mutate": {
            TypesMutation.CREATE.value: ("input_object_type_for_create", f"Create{singular_camel_case_name}Input"),
            TypesMutation.UPDATE.value: ("input_object_type_for_update", f"Update{singular_camel_case_name}Input"),
            TypesMutation.CREATE_UPDATE.value: ("input_object_type", f"{singular_camel_case_name}Input"),
        },
        "filter": ("input_object_type_for_filter", f"{singular_camel_case_name}FilterInput"),
        "order_by": ("input_object_type_for_order", f"{singular_camel_case_name}OrderByInput"),
    }

    if purpose == "mutate":
        return input_type_map[purpose][type_mutation]
    else: # filter, order_by
        return input_type_map[purpose]

def get_input_fields(model: DjangoModel, registry: RegistryGlobal, purpose:TypePurposeInputFields, type_mutation:TypesMutation=None, meta_attrs:Dict={}):

    input_fields = OrderedDict()
    if purpose == "mutate":
        type_input = "for_mutate"
        model_fields = get_model_fields(model=model, for_mutation=True, only_fields=meta_attrs.get("only_fields", meta_attrs.get("only", meta_attrs.get("fields", "__all__"))), exclude_fields=meta_attrs.get("exclude_fields", meta_attrs.get("exclude", ())))
        field_pk = model._meta.pk
        converted_pk = convert_django_field_with_choices(field=field_pk, purpose=FieldPurposeConvert.INPUT.value, registry=registry, convert_choices_to_enum=True, type_input=type_input)
        if converted_pk:
            if type_mutation == TypesMutation.UPDATE.value:
                converted_pk.kwargs.update({"required": True})
                input_fields[field_pk.name] = converted_pk
            elif type_mutation == TypesMutation.CREATE_UPDATE.value:
                converted_pk.kwargs.update({"required": False})
                input_fields[field_pk.name] = converted_pk
        else:
            if type_mutation == TypesMutation.UPDATE.value:
                input_fields[field_pk.name] = graphene.ID(required=True)
            elif type_mutation == TypesMutation.CREATE_UPDATE.value:
                input_fields[field_pk.name] = graphene.ID()

        

    elif purpose == "filter":
        type_input = "for_search"
        model_fields = get_model_fields(model=model, for_queryset=True, only_fields=meta_attrs.get("only_fields", "__all__"), exclude_fields=meta_attrs.get("exclude_fields", ()))
        input_fields.update({
            "AND": graphene.Dynamic(lambda: graphene.InputField(graphene.List(get_input_object_type(model, 'filter')))),
            "OR": graphene.Dynamic(lambda: graphene.InputField(graphene.List(get_input_object_type(model, 'filter')))),
            "NOT": graphene.Dynamic(lambda: graphene.InputField(get_input_object_type(model, 'filter')))
        })
    elif purpose == "order_by":
        type_input = "for_order_by"
        model_fields = get_model_fields(model=model, for_queryset=True, only_fields=meta_attrs.get("only_fields", "__all__"), exclude_fields=meta_attrs.get("exclude_fields", ()))
    
    for name, field in model_fields:
        converted_field = convert_django_field_with_choices(field=field, purpose=FieldPurposeConvert.INPUT.value, registry=registry, convert_choices_to_enum=True, type_input=type_input)
        hold_required = meta_attrs.get("hold_required_in_fields", True)

        if type_mutation == TypesMutation.UPDATE.value or type_mutation == TypesMutation.CREATE_UPDATE.value:
            hold_required = meta_attrs.get("hold_required_in_fields", False)
            kw = getattr(converted_field, "kwargs", None)
            if kw and not hold_required:
                if "required" in converted_field.kwargs:
                    converted_field.kwargs["required"] = False

        input_fields[name] = converted_field
    return input_fields

def get_input_object_type(model, purpose, type_mutation:TypesMutation=None, meta_attrs={}, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    registry = get_global_registry()
    names_of_model = get_name_of_model_in_different_case(model, prefix=prefix_for_name, suffix=suffix_for_name)
    singular_camel_case_name = names_of_model.get("camel_case")
    registries_for_model = registry.get_registry_for_model(model)
    
    type_input_object_type, name_for_input_object_type = get_type_and_name_input(purpose, type_mutation, singular_camel_case_name)
    
    if registries_for_model is not None and type_input_object_type in registries_for_model:
        return registries_for_model[type_input_object_type]
    
    input_fields = get_input_fields(model, registry, purpose, type_mutation, meta_attrs)

    attrs_final = transform_args_type_relation(model, { **input_fields, **extra_attrs }, registry, type_mutation)
    
    ModelInputObjectType = build_class(
        name=name_for_input_object_type,
        bases=(graphene.InputObjectType,),
        attrs=attrs_final
    )
    registry.register_model(model, type_input_object_type, ModelInputObjectType)
    return ModelInputObjectType

def convert_model_fields_to_mutation_input_fields(model: DjangoModel, registry:RegistryGlobal, for_type_mutation:TypesMutation=TypesMutation.CREATE.value, meta_attrs={}):
    return get_input_fields(model=model, registry=registry, purpose='mutate', type_mutation=for_type_mutation, meta_attrs=meta_attrs)

def convert_model_to_mutation_input_object_type(model:DjangoModel, type_mutation:TypesMutation=TypesMutation.CREATE.value, meta_attrs={}, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    return get_input_object_type(
        model=model, 
        purpose='mutate', 
        type_mutation=type_mutation, 
        meta_attrs=meta_attrs,
        extra_attrs=extra_attrs,
        prefix_for_name=prefix_for_name, 
        suffix_for_name=suffix_for_name
    )

def convert_model_to_filter_input_object_type(model:DjangoModel, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    return get_input_object_type(
        model=model,
        purpose='filter',
        extra_attrs=extra_attrs,
        prefix_for_name=prefix_for_name,
        suffix_for_name=suffix_for_name
    )

def convert_model_to_order_by_input_object_type(model:DjangoModel, extra_attrs={}, prefix_for_name="", suffix_for_name=""):
    return get_input_object_type(
        model=model, 
        purpose='order_by', 
        extra_attrs=extra_attrs, 
        prefix_for_name=prefix_for_name, 
        suffix_for_name=suffix_for_name
    )

def nested_get(input_dict, nested_key):
    internal_dict_value = input_dict
    for k in nested_key:
        internal_dict_value = internal_dict_value.get(k, None)
        if internal_dict_value is None:
            return None
    return internal_dict_value

def get_real_id(value):
    return value

    # try:
    #     gql_type, relay_id = from_global_id(value)
    #     if registry.get_django_type(gql_type) is not None:
    #         return relay_id
    #     else:
    #         return value
    # except:
    #     return value

def get_paths(d):
    """Breadth-First Search"""
    queue = [(d, [])]
    while queue:
        actual_node, p = queue.pop(0)
        yield p
        if isinstance(actual_node, dict):
            for k, v in actual_node.items():
                queue.append((v, p + [k]))

def get_args(where):
    args = {}
    for path in get_paths(where):
        arg_value = nested_get(where, path)
        if not isinstance(arg_value, dict):
            arg_key = "__".join(path)
            if arg_key.endswith("__equals"):
                arg_key = arg_key[0:-8] + "__exact"
            if ( arg_key == "id__exact" or arg_key.endswith("__id__exact") or arg_key == "id__in" or arg_key.endswith("__id__in") ):
                if isinstance(arg_value, list):
                    try:
                        arg_value = [get_real_id(value) for value in arg_value]
                    except:
                        pass
                else:
                    try:
                        arg_value = get_real_id(arg_value)
                    except:
                        pass

            args[arg_key] = arg_value
    return args

def where_input_to_Q(where):

    AND = Q()
    OR = Q()
    NOT = Q()

    if "OR" in where.keys():
        for w in where.pop("OR"):
            OR = OR | Q(where_input_to_Q(w))

    if "AND" in where.keys():
        for w in where.pop("AND"):
            AND = AND & Q(where_input_to_Q(w))

    if "NOT" in where.keys():
        NOT = NOT & ~Q(where_input_to_Q(where.pop("NOT")))

    return Q(**get_args(where)) & OR & AND & NOT

def order_by_input_to_args(order_by):
    args = []
    for rule in order_by:
        for path in get_paths(rule):
            v = nested_get(rule, path)
            if not isinstance(v, dict):
                if v == "ASC":
                    args.append("__".join(path))
                elif v == "DESC":
                    args.append("-" + "__".join(path))
                elif v == "IASC":
                    args.append(Lower("__".join(path)).asc())
                elif v == "IDESC":
                    args.append(Lower("__".join(path)).desc())
    return args

def get_where_arg(model, kw={}, default_required=False, prefix="", suffix=""):
    attrs_for_where_arg = kw.get("modify_where_argument", {})
    model_as_filter_input_object_type = convert_model_to_filter_input_object_type(
        model=model, 
        #TODO: extra_meta_attrs={ "fields": attrs_for_where_arg.get("only_fields", "__all__"), "exclude": attrs_for_where_arg.get("exclude_fields", None), },
        extra_attrs=attrs_for_where_arg.get("extra_fields", {}), 
        prefix_for_name=prefix, 
        suffix_for_name=suffix
    )
    default_values_for_where = {
        "type_": model_as_filter_input_object_type,
        "name": "where",
        "required": default_required,
        "description": ""
    }
    for key in default_values_for_where.keys():
        if key in attrs_for_where_arg:
            default_values_for_where[key] = attrs_for_where_arg[key]        
    if default_values_for_where.get("hidden", False):
        return {}
    else:
        return {"where": graphene.Argument(**default_values_for_where)}

def get_order_by_arg(model, kw={}, prefix="", suffix=""):
    attrs_for_order_by_arg = kw.get("modify_order_by_argument", {})
    model_as_order_by_input_object_type = convert_model_to_order_by_input_object_type(
        model=model, 
        #TODO: extra_meta_attrs={ "fields": attrs_for_order_by_arg.get("only_fields", "__all__"), "exclude": attrs_for_order_by_arg.get("exclude_fields", None), },
        extra_attrs=attrs_for_order_by_arg.get("extra_fields", {}), 
        prefix_for_name=prefix, 
        suffix_for_name=suffix
    )
    default_values_for_order_by = {
        "type_": model_as_order_by_input_object_type,
        "name": "orderBy",
        "required": False,
        "description": ""
    }
    for key in default_values_for_order_by.keys():
        if key in attrs_for_order_by_arg:
            default_values_for_order_by[key] = attrs_for_order_by_arg[key]        
    if default_values_for_order_by.get("hidden", False):
        return {}
    else:
        return {"order_by": graphene.Argument(**default_values_for_order_by)}

def get_paginated_arg(kw={}):
    default_values_for_paginated = {
        "type_": PaginatedInput,
        "name": "paginated",
        "required": False,
        "description": "",
    }
    attrs_for_paginated_arg = kw.get("modify_paginated_argument", {})
    attrs_for_paginated_arg = default_values_for_paginated|attrs_for_paginated_arg
    if default_values_for_paginated.get("hidden", False):
        return {}
    else:
        return {"paginated": graphene.Argument(**default_values_for_paginated)}

def transform_args_type_relation(model: DjangoModel, args_final, registry: RegistryGlobal, type_mutation_input):
    from cruddals_django.converter.converter_input_relation import convert_relation_field_to_input

    for arg, value in args_final.items():
        if isinstance(value, CruddalsRelationField):
            try:
                django_field = model._meta.get_field(arg)
                relation_input_object_type = convert_relation_field_to_input(
                    django_field,
                    registry=registry,
                    type_mutation_input=type_mutation_input,
                )
                args_final[arg] = relation_input_object_type
            except Exception as e:
                warnings.warn(message=str(e))
    
    return args_final

def validate_instance_and_get_errors(instance):
    try:
        instance.full_clean()
    except ValidationError as e:
        # 'e' es una instancia de ValidationError.
        # El atributo 'message_dict' de 'e' es un diccionario que mapea
        # los nombres de los campos a los mensajes de error para esos campos.
        return e.message_dict
    # Si no se lanza ninguna excepción, eso significa que la instancia es válida.
    return None

def is_list_of_same_type(list_elements, target_class):
    return all(isinstance(element, target_class) for element in list_elements)

def get_field_values_from_instances(instance_list, field_name):
    field_values = []
    for instance in instance_list:
        if hasattr(instance, field_name):
            field_values.append(getattr(instance, field_name))
        else:
            raise ValueError(f"El campo '{field_name}' no existe en el modelo {type(instance).__name__}")
    return field_values

def get_list_input_object_type(value_of_field_to_convert, related_model):
    list_values = []
    list_values_to_modify = []
    list_values_to_connect = []
    list_values = [value_of_field_to_convert] if not isinstance(value_of_field_to_convert, list) else value_of_field_to_convert
    pk_field_name = related_model._meta.pk.name
    
    if is_list_of_same_type(list_values, graphene.InputObjectType):
        list_values_to_modify = [value for value in list_values if pk_field_name not in value]
        list_values_to_connect = [value for value in list_values if pk_field_name in value]
    
    return list_values_to_modify, list_values_to_connect

def get_mutations_for_model(model, registry):
    registries_for_model = registry.get_registry_for_model(model)
    if registries_for_model:
        cruddals_for_related_model = registries_for_model.get("cruddals", None)
        if cruddals_for_related_model:
            mutation_for_create = cruddals_for_related_model.meta.mutation_create
            mutation_for_update = cruddals_for_related_model.meta.mutation_update
            return mutation_for_create, mutation_for_update

def create_direct_relation_model_objects(obj_to_relate, list_objects_to_relate, name_field_relate, field_relation, direct_field_detail, mutation, root, info):
    response_direct_objs = mutation.mutate_and_get_payload(root, info, list_objects_to_relate)
    if response_direct_objs.objects:
        reverse_pks = get_field_values_from_instances(response_direct_objs.objects, "pk")
        if isinstance( field_relation, (ForeignKey, OneToOneField) ):
            obj_to_relate[name_field_relate] = reverse_pks[0]
        elif isinstance( field_relation, (ManyToManyField) ):
            actual_reverse_pks_of_direct_obj = []
            if direct_field_detail["pk_field_name"] in obj_to_relate:
                direct_pk_value = obj_to_relate[direct_field_detail["pk_field_name"]]
                direct_actual_obj = direct_field_detail["model"].objects.get(pk=direct_pk_value)
                query_set_actual_objs_related:QuerySet = getattr(direct_actual_obj, direct_field_detail["name_field"]).all()
                actual_reverse_pks_of_direct_obj = list(query_set_actual_objs_related.values_list("pk", flat=True))
            obj_to_relate[name_field_relate] = reverse_pks + actual_reverse_pks_of_direct_obj
    return response_direct_objs

def create_reverse_relation_model_objects(pk_obj_to_relate, list_objects_to_relate, name_field_relate, field_relation, direct_field_detail, mutation, root, info):
    for obj_to_relate in list_objects_to_relate:
        if isinstance( field_relation, (ManyToOneRel, OneToOneRel) ):
            obj_to_relate[name_field_relate] = pk_obj_to_relate
        
        elif isinstance( field_relation, (ManyToManyRel) ):
            actual_pks_of_obj_to_relate = []
            if getattr(obj_to_relate, direct_field_detail["pk_field_name"], None):
                reverse_pk_value = getattr(obj_to_relate, direct_field_detail["pk_field_name"]) # ===> Equivalente QuestionDetail(id=1) = id=1
                reverse_actual_obj = direct_field_detail["model"].objects.get(pk=reverse_pk_value)  # ===> QuestionDetail.objects.get(pk=)
                query_set_reverse_actual_objs:QuerySet = getattr(reverse_actual_obj, direct_field_detail["name_field"]).all()
                actual_pks_of_obj_to_relate = list(query_set_reverse_actual_objs.values_list("pk", flat=True))
            
            obj_to_relate[name_field_relate] = [pk_obj_to_relate] + actual_pks_of_obj_to_relate
    return mutation.mutate_and_get_payload(root, info, list_objects_to_relate)

def apply_relation_mutations(type_field_relation, original_field, direct_field_detail, list_input_objects, mutation, direct_obj_to_modify, obj_modified, root, info):
    response = None
    if list_input_objects:
        if mutation:
            if type_field_relation == "field_direct":
                response = create_direct_relation_model_objects(direct_obj_to_modify, list_input_objects, direct_field_detail["name_field"], original_field, direct_field_detail, mutation, root, info)
            elif type_field_relation == "field_inverse":
                if obj_modified:
                    response = create_reverse_relation_model_objects(obj_modified.pk, list_input_objects, direct_field_detail["name_field"], original_field, direct_field_detail, mutation, root, info)
    return response

def handle_disconnect_objs_related(direct_field_detail, model, value_of_field, obj_to_modify):
    list_values_to_disconnect = []
    if "disconnect" in value_of_field:
        for value_to_disconnect in value_of_field["disconnect"]:
            obj_q = where_input_to_Q(value_to_disconnect)
            final_data = model.objects.filter(obj_q)
            final_data = list(final_data.distinct())
            list_values_to_disconnect = list_values_to_disconnect+final_data
    
    if list_values_to_disconnect:
        if isinstance( direct_field_detail["field"], (ManyToManyField, ManyToManyRel, ManyToOneRel) ):
            direct_pk_value = obj_to_modify[direct_field_detail["pk_field_name"]]
            direct_actual_obj = direct_field_detail["model"].objects.get(pk=direct_pk_value)
            getattr(direct_actual_obj, direct_field_detail["name_field"]).remove(*list_values_to_disconnect)

def get_relation_field_details(type_field_relation, django_relation_field):

    if type_field_relation == "field_direct":
        direct_model = django_relation_field.model                          # Model of field
        direct_field = django_relation_field                                # ManyToManyField, ForeignKey, OneToOneField
        direct_name_field = django_relation_field.name                      # name of field what is direct
        direct_pk_field_name = direct_model._meta.pk.name                   # pk

        reverse_model = django_relation_field.related_model                 # QuestionDetail
        reverse_field = django_relation_field.remote_field                  # ManyToManyRel, ManyToOneRel, OneToOneRel
        reverse_name_field = django_relation_field.related_query_name()     # questions,     questions,    question
        reverse_pk_field_name = reverse_model._meta.pk.name                 # pk
    
    elif type_field_relation == "field_inverse":
        direct_model = django_relation_field.related_model  # QuestionDetail
        direct_field = django_relation_field.remote_field   # ManyToManyField, ForeignKey, OneToOneField
        direct_name_field = direct_field.name               # questions,     question,    question
        direct_pk_field_name = direct_model._meta.pk.name   # pk
        
        reverse_model = django_relation_field.model         # Question
        reverse_field = django_relation_field               # ManyToManyRel, ManyToOneRel, OneToOneRel
        reverse_name_field = django_relation_field.name     # question_details, question_details, question_detail
        reverse_pk_field_name = reverse_model._meta.pk.name # pk

    return {
        "direct": {
            "model": direct_model,
            "field": direct_field,
            "name_field": direct_name_field,
            "pk_field_name": direct_pk_field_name,
        },
        "reverse": {
            "model": reverse_model,
            "field": reverse_field,
            "name_field": reverse_name_field,
            "pk_field_name": reverse_pk_field_name,
        },
    }

def create_relation_model_objects(type_field_relation, model:DjangoModel, registry:RegistryGlobal, obj_to_modify, obj_modified, root, info):
    all_model_fields = get_model_fields(model=model, for_queryset=True, for_mutation=False)
    all_model_fields = { name: field for name, field in all_model_fields }
    valid_fields = (ManyToManyField, ForeignKey, OneToOneField) if type_field_relation == "field_direct" else (ManyToManyRel, ManyToOneRel, OneToOneRel)
    fields_to_remove = []
    responses = {}
    for name_field, value_of_field in obj_to_modify.items():
        django_field = all_model_fields.get(name_field, None)
        if django_field and django_field.is_relation and isinstance(django_field, valid_fields):
            
            relation_field_details = get_relation_field_details(type_field_relation, django_field)
            model_of_django_field = relation_field_details["reverse"]["model"] if type_field_relation == "field_direct" else relation_field_details["direct"]["model"]
            mutation_for_create, mutation_for_update = get_mutations_for_model(model_of_django_field, registry)

            registries_for_model_of_django_field = registry.get_registry_for_model(model_of_django_field)
            if "input_object_type_for_connect_disconnect" in registries_for_model_of_django_field:
                input_object_type_for_connect_disconnect = registries_for_model_of_django_field["input_object_type_for_connect_disconnect"]
                if isinstance(value_of_field, input_object_type_for_connect_disconnect):
                    handle_disconnect_objs_related( relation_field_details["direct"], model_of_django_field, value_of_field, obj_to_modify ) #TODO, Que pasa si se presenta un error??
                    if "connect" in value_of_field:
                        value_of_field = value_of_field["connect"]
                        pass
                    else:
                        fields_to_remove.append(relation_field_details["direct"]["name_field"])
                        continue
            
            list_input_objects_to_create, list_input_objects_to_connect = get_list_input_object_type(value_of_field, model_of_django_field)
            
            response_create = apply_relation_mutations(type_field_relation, django_field, relation_field_details["direct"], list_input_objects_to_create, mutation_for_create, obj_to_modify, obj_modified, root, info)
            response_update = apply_relation_mutations(type_field_relation, django_field, relation_field_details["direct"], list_input_objects_to_connect, mutation_for_update, obj_to_modify, obj_modified, root, info)
            
            responses[name_field] = {
                "create": response_create,
                "update": response_update
            }
    
    for field_to_remove in fields_to_remove:
        del obj_to_modify[field_to_remove]

    return responses

def save_files_to_instance(model, instance, data):
    all_model_fields = get_model_fields(model=model, for_queryset=True, for_mutation=False)
    all_model_fields = { name: field for name, field in all_model_fields }
    for name_field, value_of_field in data.items():
        django_field = all_model_fields.get(name_field, None)
        if django_field and isinstance(django_field, (FileField, ImageField)):
            setattr(instance, name_field, value_of_field)
            instance.save()

class DjangoModelDjangoFormMutationOptions(MutationOptions):
    form_class = None
    model = None
    return_field_name = None

class ClientIDMutation(graphene.Mutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, output=None, input_fields=None, arguments={}, name=None, **options):
        input_class = getattr(cls, "Input", None)
        base_name = re.sub("Payload$", "", name or cls.__name__)
        model_name = None
        action = None
        if options is not None:
            if '_meta' in options:
                if getattr(options['_meta'], 'model', None) is not None:
                    model = options['_meta'].model
                    model_name = model.__name__
                    model_plural_name = transform_string(model._meta.verbose_name_plural, 'PascalCase') 
                    action = base_name.replace(model_plural_name, "")

        assert not output, "Can't specify any output"
        # assert not argumentss, "Can't specify any argumentss"

        final_name_for_input = f"{base_name}Input"
        if action is not None and model_name is not None:
            final_name_for_input = f"{action}{model_name}Input"

        bases = (graphene.InputObjectType,)
        if input_class:
            bases += (input_class,)
        if not input_fields:
            input_fields = {}

        cls.Input = type(final_name_for_input, bases, OrderedDict(input_fields),)

        arguments = OrderedDict(input=graphene.List(graphene.NonNull(cls.Input)), **arguments)
        mutate_and_get_payload = getattr(cls, "mutate_and_get_payload", None)

        if cls.mutate and cls.mutate.__func__ == ClientIDMutation.mutate.__func__:
            assert mutate_and_get_payload, (
                "{name}.mutate_and_get_payload method is required"
                " in a ClientIDMutation."
            ).format(name=name or cls.__name__)
        name = f"{base_name}Payload"
        super(ClientIDMutation, cls).__init_subclass_with_meta__(output=None, arguments=arguments, name=name, **options)

    @classmethod
    def mutate(cls, root, info, input, **kwargs):
        return cls.mutate_and_get_payload(root, info, input, **kwargs)

class DjangoModelFormMutation(ClientIDMutation):
    from cruddals_django.copy_graphene_django.types import ErrorsType

    class Meta:
        abstract = True

    errors = graphene.List(ErrorsType)

    @classmethod
    def __init_subclass_with_meta__( cls, form_class=None, model=None, return_field_name='objects', input_fields=None, name=None, only_fields=(), exclude_fields=(), **options):
        
        if not form_class:
            raise Exception("form_class is required for DjangoModelFormMutation")
        
        if not model:
            model = form_class._meta.model
        
        if not model:
            raise Exception("model is required for DjangoModelFormMutation")
        
        registry = get_global_registry()
        if 'registry' in options:
            if options['registry']:
                registry = options['registry']
        
        if input_fields is None:
            input_fields = get_input_fields(model=model, registry=registry, purpose=TypePurposeInputFields.MUTATE.value, type_mutation=TypesMutation.CREATE_UPDATE.value, meta_attrs={"only_fields": only_fields, "exclude_fields": exclude_fields})
        
            if "id" not in exclude_fields:
                input_fields["id"] = graphene.ID()
        
        model_type = None
        registries_for_model = registry.get_registry_for_model(model)
        if registries_for_model is not None and "object_type" in registries_for_model:
            model_type = registries_for_model["object_type"]

        if not model_type:
            raise Exception("No type registered for model: {}".format(model.__name__))
        if not return_field_name:
            return_field_name = model._meta.verbose_name_plural
        output_fields = OrderedDict()
        output_fields[return_field_name] = graphene.List(model_type)

        if name is None:
            name = "%sForm" % model.__name__

        _meta = DjangoModelDjangoFormMutationOptions(cls)
        _meta.form_class = form_class
        _meta.model = model
        _meta.return_field_name = return_field_name
        _meta.fields = yank_fields_from_attrs(output_fields, _as=graphene.Field)

        input_fields = yank_fields_from_attrs(input_fields, _as=graphene.InputField)
        super(DjangoModelFormMutation, cls).__init_subclass_with_meta__(_meta=_meta, name=name, input_fields=input_fields, **options)

    @classmethod
    def get_form(cls, root, info, input):
        file_kwargs = {"files": MultiValueDict()}
        model:DjangoModel = cls._meta.model
        for key, value in input.items():
            django_field:DjangoField = model._meta.get_field(key)
            if isinstance(django_field, (FileField, ImageField)) and not isinstance(value, str):
                file_kwargs["files"].setlist(key, [value])
        input = {key: value.value if issubclass(type(value), (graphene.Enum, Enum)) else value for key, value in input.items()}
        form_kwargs = cls.get_form_kwargs(root, info, input)
        form_kwargs = {**form_kwargs, **file_kwargs}
        return cls._meta.form_class(**form_kwargs)

    @classmethod
    def get_form_kwargs(cls, root, info, input):
        kwargs = {"data": input}
        pk = input.pop("id", None)
        if pk:
            instance = cls._meta.model._default_manager.get(pk=pk)
            kwargs["instance"] = instance
        return kwargs

    @classmethod
    def mutate_and_get_payload(cls, root, info, input, **kwargs):
        registry = get_global_registry()
        arr_obj = []
        arr_errors = []
        object_counter = 0
        for obj_to_modify in input:
            with transaction.atomic():
                internal_arr_errors = []
                model: DjangoModel = cls._meta.model
                responses_direct = create_relation_model_objects("field_direct", model, registry, obj_to_modify, None, root, info)
                for name_related_field, obj in responses_direct.items():
                    for response in obj.values():
                        if response:
                            if response.errors:
                                for related_error in response.errors:
                                    setattr(related_error, 'object_position', object_counter)
                                    for internal_related_error in related_error.errors:
                                        setattr(internal_related_error, 'field', f"{to_camel_case(name_related_field)}.{internal_related_error.field}")
                                internal_arr_errors.extend(response.errors)
                if len(internal_arr_errors) > 0:
                    arr_errors.extend(internal_arr_errors)
                    continue
                form:DjangoModelForm = cls.get_form(root, info, obj_to_modify)
                if form.is_valid():
                    instance = form.save()
                    responses_reverse = create_relation_model_objects("field_inverse", model, registry, obj_to_modify, instance, root, info)
                    for name_related_field, obj in responses_reverse.items():
                        for response in obj.values():
                            if response:
                                if response.errors:
                                    for related_error in response.errors:
                                        setattr(related_error, 'object_position', object_counter)
                                        for internal_related_error in related_error.errors:
                                            setattr(internal_related_error, 'field', f"{to_camel_case(name_related_field)}.{internal_related_error.field}")
                                    internal_arr_errors.extend(response.errors)
                                    transaction.set_rollback(True)

                    if len(internal_arr_errors) > 0:
                        arr_errors.extend(internal_arr_errors)
                        continue
                    arr_obj.append(instance)
                else:
                    errors = ErrorType.from_errors(form.errors)
                    e = ErrorsType.from_errors(object_counter, errors)
                    arr_errors.append(e)
                    if info and info.context:
                        setattr(info.context, MUTATION_ERRORS_FLAG, True)
                    transaction.set_rollback(True)
            object_counter = object_counter + 1
        if len(arr_obj) == 0:
            arr_obj = None
        if len(arr_errors) == 0:
            arr_errors = None
        kwargs = {cls._meta.return_field_name: arr_obj}
        return cls(errors=arr_errors, **kwargs)
