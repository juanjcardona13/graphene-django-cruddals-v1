from enum import Enum
from functools import wraps
from collections import OrderedDict

import graphene

from graphene_django_cruddals_v1.registry.registry_global import RegistryGlobal

from ..copy_graphene_django.settings import graphene_settings

from graphql import GraphQLError
from graphql import assert_name
from graphene.utils.str_converters import to_camel_case
from django.utils.module_loading import import_string
from django.utils.encoding import force_str


class FieldPurposeConvert(Enum):
    INPUT = "input"
    OUTPUT = "output"


class BlankValueField(graphene.Field):
    def wrap_resolve(self, parent_resolver):
        resolver = self.resolver or parent_resolver

        # create custom resolver
        def blank_field_wrapper(func):
            @wraps(func)
            def wrapped_resolver(*args, **kwargs):
                return_value = func(*args, **kwargs)
                if return_value == "":
                    return None
                return return_value

            return wrapped_resolver

        return blank_field_wrapper(resolver)


def get_django_field_description(field):
    return str(field.help_text) if field.help_text else None


def convert_choice_name(name):
    from graphene_django_cruddals_v1.utils.utils import to_const

    name = to_const(force_str(name))
    try:
        assert_name(name)
    except GraphQLError:
        name = "A_%s" % name
    return name


def get_choices(choices):
    converted_names = []
    if isinstance(choices, OrderedDict):
        choices = choices.items()
    for value, help_text in choices:
        if isinstance(help_text, (tuple, list)):
            yield from get_choices(help_text)
        else:
            name = convert_choice_name(value)
            while name in converted_names:
                name += "_" + str(len(converted_names))
            converted_names.append(name)
            description = str(
                help_text
            )  # TODO: translatable description: https://github.com/graphql-python/graphql-core-next/issues/58
            yield name, value, description


def convert_choices_to_named_enum_with_descriptions(name, choices):
    choices = list(get_choices(choices))
    named_choices = [(c[0], c[1]) for c in choices]
    named_choices_descriptions = {c[0]: c[2] for c in choices}

    class EnumWithDescriptionsType:
        @property
        def description(self):
            return str(named_choices_descriptions[self.name])

    return_type = graphene.Enum(
        name,
        list(named_choices),
        type=EnumWithDescriptionsType,
        description="An enumeration.",  # Temporary fix until https://github.com/graphql-python/graphene/pull/1502 is merged
    )
    return return_type


def generate_enum_name(django_model_meta, field):
    if graphene_settings.DJANGO_CHOICE_FIELD_ENUM_CUSTOM_NAME:
        # Try and import custom function
        custom_func = import_string( graphene_settings.DJANGO_CHOICE_FIELD_ENUM_CUSTOM_NAME )
        name = custom_func(field)
    elif graphene_settings.DJANGO_CHOICE_FIELD_ENUM_V2_NAMING is True:
        name = to_camel_case(f"{django_model_meta.object_name}_{field.name}")
    else:
        name = "{app_label}{object_name}{field_name}Choices".format(
            app_label=to_camel_case(django_model_meta.app_label.title()),
            object_name=django_model_meta.object_name,
            field_name=to_camel_case(field.name.title()),
        )
    return name


def convert_choice_field_to_enum(field, name=None):
    if name is None:
        name = generate_enum_name(field.model._meta, field)
    choices = field.choices
    return convert_choices_to_named_enum_with_descriptions(name, choices)


def convert_django_field_with_choices( field, purpose:FieldPurposeConvert=FieldPurposeConvert.OUTPUT.value, registry:RegistryGlobal=None, convert_choices_to_enum=True, type_input=None ):
    if registry is not None:
        converted = None
        registries_for_field = registry.get_registry_for_field(field)
        if registries_for_field is not None and purpose in registries_for_field:
            converted = registries_for_field[purpose]
        if converted:
            return converted
    choices = getattr(field, "choices", None)
    if choices and convert_choices_to_enum:
        EnumCls = convert_choice_field_to_enum(field)
        required = not (field.blank or field.null)

        converted = EnumCls( description=get_django_field_description(field), required=required ).mount_as(BlankValueField)
    else:
        from graphene_django_cruddals_v1.converter.converter_input import convert_django_field_to_input
        from graphene_django_cruddals_v1.converter.converter_output import convert_django_field
        
        if purpose == FieldPurposeConvert.INPUT.value:
            converted = convert_django_field_to_input(field, registry, type_input)
            if registry is not None:
                registry.register_field(field, f"{purpose}_{type_input}", converted)
        elif purpose == FieldPurposeConvert.OUTPUT.value:
            converted = convert_django_field(field, registry)
            if registry is not None:
                registry.register_field(field, purpose, converted)
    return converted
