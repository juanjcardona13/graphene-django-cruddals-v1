# # -*- coding: utf-8 -*-
from collections import OrderedDict
from enum import Enum
from django.apps import apps as django_apps
from django.db.models import (
    NOT_PROVIDED,
    Q,
    QuerySet,
    Model as DjangoModel,
    ManyToOneRel,
    ManyToManyRel,
    OneToOneRel,
    ManyToManyField,
    ForeignKey, 
    OneToOneField
)

import graphene
from graphene.utils.subclass_with_meta import SubclassWithMeta
from graphene.utils.props import props
from graphql import GraphQLError
from graphene_django_cruddals_v1.copy_graphene_django.fields import DjangoListField

from graphene_django_cruddals_v1.copy_graphene_django.types import ErrorsType

from .utils.utils import (
                    DjangoModelFormMutation, add_cruddals_model_to_request, build_class, 
                    convert_model_fields_to_mutation_input_fields, convert_model_to_model_form, convert_model_to_mutation_input_object_type, convert_model_to_object_type, convert_model_to_paginated_object_type, 
                    delete_keys, get_global_registry, get_name_of_model_in_different_case, get_order_by_arg, get_paginated_arg, get_where_arg, maybe_queryset, order_by_input_to_args, toggle_active_status, transform_args_type_relation, update_dict_with_model_instance, 
                    paginate_queryset, merge_dict, validate_list_func_cruddals, where_input_to_Q
                )
from .settings import cruddals_settings


# For interfaces, is executed first AppInterface, after Model Interface, for both is executed in order of list

CLASS_CRUDDALS_NAMES = ["Create", "Read", "Update", "Delete", "Deactivate", "Activate", "List", "Search"]
CLASS_TYPE_NAMES = ["InputObjectType", "ObjectType"]
FINAL_CLASS_NAMES = CLASS_CRUDDALS_NAMES + CLASS_TYPE_NAMES

class CruddalsInterfaceNames(Enum):
    CREATE = "Create"
    READ = "Read"
    UPDATE = "Update"
    DELETE = "Delete"
    DEACTIVATE = "Deactivate"
    ACTIVATE = "Activate"
    LIST = "List"
    SEARCH = "Search"

    INPUT_OBJECT_TYPE = "InputObjectType"
    OBJECT_TYPE = "ObjectType"


class BuilderBase:

    def get_interface_attrs(self, Interface, include_meta_attrs=True):
        if Interface is not None:
            attrs_internal_cls_meta = {}
            if getattr(Interface, 'Meta', None) is not None and include_meta_attrs:
                attrs_internal_cls_meta = props(Interface.Meta)
            props_function = delete_keys(props(Interface), ['Meta'])
            return {**props_function, **attrs_internal_cls_meta}
        return {}

    def get_interface_meta_attrs(self, InterfaceType):
        if InterfaceType is not None:
            if getattr(InterfaceType, 'Meta', None) is not None:
                p = props(InterfaceType.Meta)
                
                fields = p.get('fields', p.get('only_fields', p.get('only', [])))
                exclude = p.get('exclude', p.get('exclude_fields', p.get('exclude', [])))
                assert not (fields and exclude), (f"Cannot set both 'fields' and 'exclude' options on Type {self.name_camel_case}.")
                return p
        return {}

    def validate_attrs(self, props, function_name, operation_name, class_name=None):
        class_name = class_name or self.name_camel_case
        function_name_without = function_name.replace("override_total_", "")
        model_pre = props.get(f'pre_{function_name_without}')
        model_function = props.get(f'{function_name_without}')
        model_override_function = props.get(f'{function_name}')
        model_post = props.get(f'post_{function_name_without}')

        assert not (model_pre and model_override_function), ( f"Cannot set both 'pre_{function_name_without}' and '{function_name}' options on {operation_name} {class_name}." )
        assert not (model_function and model_override_function), ( f"Cannot set both '{function_name_without}' and '{function_name}' options on {operation_name} {class_name}." )
        assert not (model_post and model_override_function), ( f"Cannot set both 'post_{function_name_without}' and '{function_name}' options on {operation_name} {class_name}." )

    def get_function_lists(self, key, kwargs, func_default):
        functions = kwargs.get(key, [func_default])
        if not callable(func_default):
            raise ValueError(f"func_default must be a function, but got {type(func_default)}")
        if not isinstance(functions, list):
            functions = [functions]
        return functions

    def get_last_element(self, key, kwargs, default=None):
        if key in kwargs:
            element = kwargs[key]
            if isinstance(element, list):
                return element[-1]
            return element
        return default

    def get_extra_arguments(self, kwargs):
        return kwargs.get('extra_arguments', {})

    def save_pre_post_how_list(self, kwargs):
        for attr, value in kwargs.items():
            if 'pre' in attr or 'post' in attr:
                if not isinstance(kwargs[attr], list):
                    kwargs[attr] = [value]


class BuilderQuery(BuilderBase):

    def get_final_resolve(self, kwargs, resolve):
        return self.get_last_element("override_total_resolve", kwargs, resolve)

    def get_pre_and_post_resolves(self, kwargs):
        pre_default = lambda cls, info, **kwargs : (cls, info, kwargs)
        post_default = lambda cls, info, default_response, **kwargs : default_response

        pre_resolves_model = self.get_function_lists('pre_resolve', kwargs, pre_default)
        post_resolves_model = self.get_function_lists('post_resolve', kwargs, post_default)
        return pre_resolves_model, post_resolves_model


class BuilderMutation(BuilderBase):
    
    def get_state_controller_field(self, kwargs) -> str:
        return self.get_last_element("state_controller_field", kwargs, cruddals_settings.ACTIVE_INACTIVE_STATE_CONTROLLER_FIELD)

    def get_final_mutate(self, kwargs, mutate):
        return self.get_last_element("override_total_mutate", kwargs, mutate)

    def get_pre_and_post_mutates(self, kwargs,):
        pre_default = lambda cls, root, info, data, **kwargs: (cls, root, info, data, kwargs)
        post_default = lambda cls, root, info, data=None, default_response=None, **kwargs: default_response

        pre_mutates_model = self.get_function_lists('pre_mutate', kwargs, pre_default)
        post_mutates_model = self.get_function_lists('post_mutate', kwargs, post_default)

        return pre_mutates_model, post_mutates_model
    

class BuilderCreate(BuilderMutation):

    def get_arg_for_create_default(self, kwargs):
        registry = get_global_registry()
        modify_input_argument = kwargs.get("modify_input_argument", {})
        fields = modify_input_argument.get('only_fields', "__all__")
        exclude = modify_input_argument.get('exclude_fields', ())
        
        arguments_create_model_input = convert_model_fields_to_mutation_input_fields(model=self.model, registry=registry, meta_attrs={"only_fields": fields, "exclude_fields": exclude})
        arguments_for_model_input = modify_input_argument.get("extra_fields", {})
        args_final = {**arguments_create_model_input, **arguments_for_model_input}
        args_final = transform_args_type_relation(model=self.model, args_final=args_final, registry=registry, type_mutation_input="create")
        return args_final

    def validate_props_create(self, props, name=None):
        self.validate_attrs(props, 'override_total_mutate', 'Create', name)

    def get_fun_mutate_for_create(self, kw):
        mutate_default = lambda cls, root, info, data, **kwargs: super(cls, cls()).mutate_and_get_payload(root, info, data, **kwargs)
        pre_mutates_model, post_mutates_model = self.get_pre_and_post_mutates(kw)
        mutate_model = self.get_last_element('mutate', kw, mutate_default)
        
        def mutate_create(cls, root, info, input=None, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_mutate_create in pre_mutates_model:
                cls, root, info, input, kwargs = pre_mutate_create(cls, root, info, input, **kwargs)
            response = mutate_model(cls, root, info, input, **kwargs)
            for post_mutate_create in post_mutates_model:
                response = post_mutate_create(cls, root, info, input, response, **kwargs)
            return response
        
        return self.get_final_mutate(kw, mutate_create)

    def build_create( self, **attrs_for_build_the_create ):
        arg_for_create_default = self.get_arg_for_create_default(attrs_for_build_the_create)
        extra_arg_for_create = self.get_extra_arguments(attrs_for_build_the_create)
        
        mutation_create = self.get_fun_mutate_for_create(attrs_for_build_the_create)
        
        MetaCreate = build_class(
            name='Meta', 
            attrs={
                "name": f"Create{self.name_plural_camel_case}", 
                "form_class": self.model_as_form, 
                "input_fields": arg_for_create_default, 
                "arguments": extra_arg_for_create,
                "registry": get_global_registry(f"{self.prefix}{self.suffix}")
            }
        )
        CreateCustom = build_class(
            name=f'Create{self.name_plural_camel_case}', 
            bases=(DjangoModelFormMutation,), 
            attrs={
                "Meta": MetaCreate, 
                "mutate_and_get_payload": classmethod(mutation_create)
            }
        )
        return CreateCustom


class BuilderRead(BuilderQuery):

    def validate_props_read(self, props, name=None):
        self.validate_attrs(props, 'override_total_resolve', 'Read', name)

    def get_fun_resolve_for_read(self, kwargs):
        
        def resolve_default(cls, info, **kwargs):
            final_data:QuerySet = self.model.objects.all()
            final_data = maybe_queryset(self.model_as_object_type.get_queryset(final_data, info))
            if "where" in kwargs.keys():
                where = kwargs["where"] 
                obj_q = where_input_to_Q(where)
                final_data = final_data.filter(obj_q)
                final_data = final_data.distinct()
            return final_data.get()
        
        pre_resolves_read, post_resolves_read = self.get_pre_and_post_resolves(kwargs)
        resolve_model = self.get_last_element('resolve', kwargs, resolve_default)

        def resolve_read(cls, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_resolve_read in pre_resolves_read:
                cls, info, kwargs = pre_resolve_read(cls, info, **kwargs)
            response = resolve_model(cls, info, **kwargs)
            for post_resolve_read in post_resolves_read:
                response = post_resolve_read(cls, info, response, **kwargs)
            return response
        
        return self.get_final_resolve(kwargs, resolve_read)

    def build_read( self, **kwargs ):
        extra_arg_for_read = self.get_extra_arguments(kwargs)
        where_arg = get_where_arg(model=self.model, kw=kwargs, default_required=True, prefix=self.prefix, suffix=self.suffix)
        read_custom = graphene.Field(
            self.model_as_object_type, 
            name=f"read{self.name_camel_case}", 
            args={
                **where_arg, 
                **extra_arg_for_read
            }
        )
        resolve = self.get_fun_resolve_for_read(kwargs)
        return read_custom, resolve


class BuilderUpdate(BuilderMutation):

    def get_arg_for_update_default(self, kwargs):
        registry = get_global_registry()
        modify_input_argument = kwargs.get("modify_input_argument", {})
        fields = modify_input_argument.get('only_fields', "__all__")
        exclude = modify_input_argument.get('exclude_fields', ())

        arguments_update_model_input = convert_model_fields_to_mutation_input_fields(model=self.model, registry=registry, meta_attrs={"only_fields": fields, "exclude_fields": exclude}, for_type_mutation="update")
        arguments_for_model_input = modify_input_argument.get("extra_fields", {})
        args_final = {**arguments_update_model_input, **arguments_for_model_input}
        args_final = transform_args_type_relation(model=self.model, args_final=args_final, registry=registry, type_mutation_input="update")
        return args_final
    
    def validate_props_update(self, props, name=None):
        self.validate_attrs(props, 'override_total_mutate', 'Update', name)

    def get_fun_mutate_for_update(self, kw):
        
        def mutate_default(cls, root, info, input, **kwargs):
            new_input = [update_dict_with_model_instance(old_input, cls) for old_input in input]
            return super(cls, cls()).mutate_and_get_payload(root, info, new_input, **kwargs)        
        
        pre_mutates_model, post_mutates_model = self.get_pre_and_post_mutates(kw)
        mutate_model = self.get_last_element('mutate', kw, mutate_default)
        
        def mutate_update(cls, root, info, input=None, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_mutate in pre_mutates_model:
                cls, root, info, input, kwargs = pre_mutate(cls, root, info, input, **kwargs)
            response = mutate_model(cls, root, info, input, **kwargs)
            for post_mutate in post_mutates_model:
                response = post_mutate(cls, root, info, input, response, **kwargs)
            return response
        
        return self.get_final_mutate(kw, mutate_update)

    def build_update( self, **attrs_for_build_the_update ):
        arg_for_update_default = self.get_arg_for_update_default(attrs_for_build_the_update)
        extra_arg_for_update = self.get_extra_arguments(attrs_for_build_the_update)
        mutation_update = self.get_fun_mutate_for_update(attrs_for_build_the_update)
        MetaUpdate = build_class(
            name='Meta', 
            attrs={
                "name": f"Update{self.name_plural_camel_case}",
                "form_class": self.model_as_form,
                "input_fields": arg_for_update_default,
                "arguments": extra_arg_for_update,
                "registry": get_global_registry(f"{self.prefix}{self.suffix}")
            }
        )
        UpdateCustom = build_class(
            name=f'Update{self.name_plural_camel_case}',
            bases=(DjangoModelFormMutation,), 
            attrs={
                "Meta": MetaUpdate,
                "mutate_and_get_payload": classmethod(mutation_update)
            }
        )
        return UpdateCustom


class BuilderDelete(BuilderMutation):
    
    def validate_props_delete(self, props, name=None):
        self.validate_attrs(props, 'override_total_mutate', 'Delete', name)

    def get_fun_mutate_for_delete(self, kwargs):
        def mutate_default(cls, root, info, **kwargs):
            final_data:QuerySet = self.model.objects.all()
            if "where" in kwargs.keys():
                where = kwargs["where"] 
                obj_q = where_input_to_Q(where)
                final_data = final_data.filter(obj_q)
                final_data.delete()
                return dict(success=True)
            else:
                raise GraphQLError("Where argument is required")

            
        pre_mutates_model, post_mutates_model = self.get_pre_and_post_mutates(kwargs)
        mutate_model = self.get_last_element('mutate', kwargs, mutate_default)
        
        def mutate_delete(cls, root, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_mutate_delete in pre_mutates_model:
                cls, root, info, kwargs = pre_mutate_delete(cls, root, info, **kwargs)
            delete_response = mutate_model(cls, root, info, **kwargs)
            for post_mutate_delete in post_mutates_model:
                delete_response = post_mutate_delete(cls=cls, root=root, info=info, default_response=delete_response, **kwargs)
            return delete_response
        return self.get_final_mutate(kwargs, mutate_delete)

    def build_delete( self, **attrs_for_build_the_delete ):
        arg_for_delete = self.get_extra_arguments(attrs_for_build_the_delete)
        where_arg = get_where_arg(model=self.model, kw=attrs_for_build_the_delete, default_required=True, prefix=self.prefix, suffix=self.suffix)
        mutation_delete = self.get_fun_mutate_for_delete(attrs_for_build_the_delete)
        Meta = build_class(
            name='Meta', 
            attrs={
                'name': f"Delete{self.name_plural_camel_case}Payload", 
                'model': self.model
            }
        )
        Arguments = build_class(
            name='Arguments', 
            attrs={
                **where_arg, 
                **arg_for_delete
            }
        )
        DeleteCustom = build_class(
            name=f'Delete{self.name_plural_camel_case}',
            bases=(graphene.Mutation,), 
            attrs={
                'Arguments': Arguments,
                'Meta': Meta,
                'success': graphene.Boolean(), 
                'objects': DjangoListField(self.model_as_object_type), 
                'errors': graphene.List(ErrorsType), 
                'mutate': classmethod(mutation_delete)
            }
        )
        return DeleteCustom


class BuilderDeactivate(BuilderMutation):

    def validate_props_deactivate(self, props, name=None):
        self.validate_attrs(props, 'override_total_mutate', 'Deactivate', name)

    def get_fun_mutate_for_deactivate(self, kwargs):
        field_for_activate_deactivate:str = self.get_state_controller_field(kwargs)

        def mutate_default(cls, root, info, **kwargs):
            final_data:QuerySet = self.model.objects.all()
            if "where" in kwargs.keys():
                where = kwargs["where"] 
                obj_q = where_input_to_Q(where)
                final_data = final_data.filter(obj_q)
                final_data = final_data.distinct()
                final_data = toggle_active_status('DEACTIVATE', final_data, field_for_activate_deactivate)
                return dict(objects=final_data)
            else:
                raise GraphQLError("Where argument is required")

        pre_mutates_model, post_mutates_model = self.get_pre_and_post_mutates(kwargs)
        mutate_model = self.get_last_element('mutate', kwargs, mutate_default)

        def mutate_deactivate(cls, root, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_mutate_deactivate in pre_mutates_model:
                cls, root, info, kwargs = pre_mutate_deactivate(cls, root, info, **kwargs)
            
            deactivate_response = mutate_model(cls, root, info, **kwargs)

            for post_mutate_deactivate in post_mutates_model:
                deactivate_response = post_mutate_deactivate(cls=cls, root=root, info=info, default_response=deactivate_response, **kwargs)
            
            return deactivate_response

        return self.get_final_mutate(kwargs, mutate_deactivate)

    def build_deactivate( self, **kwargs ):
        arg_for_deactivate = self.get_extra_arguments(kwargs)
        where_arg = get_where_arg(model=self.model, kw=kwargs, default_required=True, prefix=self.prefix, suffix=self.suffix)
        mutation_deactivate = self.get_fun_mutate_for_deactivate(kwargs)
        Meta = build_class(
            name='Meta', 
            attrs={
                'name': f"Deactivate{self.name_plural_camel_case}Payload"
            }
        )
        Arguments = build_class(
            name='Arguments', 
            attrs={
                **where_arg, 
                **arg_for_deactivate
            }
        )
        DeactivateCustom = build_class(
            name=f'Deactivate{self.name_plural_camel_case}',
            bases=(graphene.Mutation,), 
            attrs={
                'Arguments': Arguments, 
                'Meta': Meta,
                'objects': DjangoListField(self.model_as_object_type), 
                'errors': graphene.List(ErrorsType), 
                'mutate': classmethod(mutation_deactivate)
            }
        )
        return DeactivateCustom


class BuilderActivate(BuilderMutation):

    def validate_props_activate(self, props, name=None):
        self.validate_attrs(props, 'override_total_mutate', 'Activate', name)

    def get_fun_mutate_for_activate(self, kwargs):
        field_for_activate_deactivate:str = self.get_state_controller_field(kwargs)
        
        def mutate_default(cls, root, info, **kwargs):
            final_data:QuerySet = self.model.objects.all()
            if "where" in kwargs.keys():
                where = kwargs["where"] 
                obj_q = where_input_to_Q(where)
                final_data = final_data.filter(obj_q)
                final_data = final_data.distinct()
                final_data = toggle_active_status('ACTIVATE', final_data, field_for_activate_deactivate)
                return dict(objects=final_data)
            else:
                raise GraphQLError("Where argument is required")
        
        pre_mutates_model, post_mutates_model = self.get_pre_and_post_mutates(kwargs)
        mutate_model = self.get_last_element('mutate', kwargs, mutate_default)

        def mutate_activate(cls, root, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_mutate_activate in pre_mutates_model:
                cls, root, info, kwargs = pre_mutate_activate(cls, root, info, **kwargs)
            
            activate_response = mutate_model(cls, root, info, **kwargs)

            for post_mutate_activate in post_mutates_model:
                activate_response = post_mutate_activate(cls=cls, root=root, info=info, default_response=activate_response, **kwargs)
            
            return activate_response

        return self.get_final_mutate(kwargs, mutate_activate)

    def build_activate( self, **kwargs ):
        extra_arg_for_activate = self.get_extra_arguments(kwargs)
        where_arg = get_where_arg(model=self.model, kw=kwargs, default_required=True, prefix=self.prefix, suffix=self.suffix)
        mutation_activate = self.get_fun_mutate_for_activate(kwargs)
        Meta = build_class(
            name='Meta',
            attrs={
                'name': f"Activate{self.name_plural_camel_case}Payload"
            }
        )
        Arguments = build_class(
            name='Arguments', 
            attrs={
                **where_arg,
                **extra_arg_for_activate
            }
        )
        ActivateCustom = build_class(
            name=f'Activate{self.name_plural_camel_case}',
            bases=(graphene.Mutation,),
            attrs={
                'Arguments': Arguments,
                'Meta': Meta,
                'objects': DjangoListField(self.model_as_object_type),
                'errors': graphene.List(ErrorsType),
                'mutate': classmethod(mutation_activate)
            }
        )
        return ActivateCustom


class BuilderList(BuilderQuery):

    def validate_props_list(self, props, name=None):
        self.validate_attrs(props, 'override_total_resolve', 'List', name)

    def get_fun_resolve_for_list(self, kwargs):
        def resolve_default(cls, info, **kwargs):
            final_data_to_paginate:QuerySet = self.model.objects.all().order_by("pk")
            
            paginated = kwargs.get("paginated", {})

            return paginate_queryset(final_data_to_paginate, paginated.get('page_size', 'All'), paginated.get('page', 1), self.paginated_object_type)
        
        pre_resolves_list, post_resolves_list = self.get_pre_and_post_resolves(kwargs)
        resolve_model = self.get_last_element('resolve', kwargs, resolve_default)
        def resolve_list(cls, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_resolve_list in pre_resolves_list:
                cls, info, kwargs = pre_resolve_list(cls, info, **kwargs)
            response = resolve_model(cls, info, **kwargs)
            for post_resolve_list in post_resolves_list:
                response = post_resolve_list(cls, info, response, **kwargs)
            return response

        return self.get_final_resolve(kwargs, resolve_list)

    def build_list( self, **kwargs ):
        extra_arg_for_list = self.get_extra_arguments(kwargs)

        order_by_arg = get_order_by_arg(model=self.model, kw=kwargs, prefix=self.prefix, suffix=self.suffix)
        paginated_arg = get_paginated_arg(kw=kwargs)
        
        list_custom = graphene.Field(
            self.paginated_object_type, 
            name=f"list{self.name_plural_camel_case}", 
            args={
                **order_by_arg,
                **paginated_arg,
                **extra_arg_for_list
            }
        )
        resolve = self.get_fun_resolve_for_list(kwargs)
        return list_custom, resolve


class BuilderSearch(BuilderQuery):

    def validate_props_search(self, props, name=None):
        self.validate_attrs(props, 'override_total_resolve', 'Search', name)
    
    def get_fun_resolve_for_search(self, kwargs):
        
        def resolve_default(cls, info, **kwargs):
            final_data_to_paginate:QuerySet = self.model.objects.all()
            
            if "where" in kwargs:
                where = kwargs["where"] 
                obj_q = where_input_to_Q(where)
                final_data_to_paginate = final_data_to_paginate.filter(obj_q)
            
            if "order_by" in kwargs or "orderBy" in kwargs:
                order_by = kwargs.get("order_by") or kwargs.get("orderBy")
                if isinstance(order_by, dict):
                    order_by = [order_by]
                list_for_order = order_by_input_to_args(order_by)
                final_data_to_paginate = final_data_to_paginate.order_by(*list_for_order)
            else:
                final_data_to_paginate = final_data_to_paginate.order_by("pk")

            paginated = kwargs.get("paginated", {})
            final_data_to_paginate = final_data_to_paginate.distinct()
            return paginate_queryset(final_data_to_paginate, paginated.get('page_size', 'All'), paginated.get('page', 1), self.paginated_object_type)
        
        pre_resolves_search, post_resolves_search = self.get_pre_and_post_resolves(kwargs)
        resolve_model = self.get_last_element('resolve', kwargs, resolve_default)

        def resolve_search(cls, info, **kwargs):
            add_cruddals_model_to_request(info, self)
            for pre_resolve_search in pre_resolves_search:
                cls, info, kwargs = pre_resolve_search(cls, info, **kwargs)

            response = resolve_model(cls, info, **kwargs)
            
            for post_resolve_search in post_resolves_search:
                response = post_resolve_search(cls, info, response, **kwargs)
            return response
        
        return self.get_final_resolve(kwargs, resolve_search)

    def build_search( self, **kwargs ):
        extra_arg_for_search = self.get_extra_arguments(kwargs)

        
        where_arg = get_where_arg(model=self.model, kw=kwargs, default_required=False, prefix=self.prefix, suffix=self.suffix)
        order_by_arg = get_order_by_arg(model=self.model, kw=kwargs, prefix=self.prefix, suffix=self.suffix)
        paginated_arg = get_paginated_arg(kw=kwargs)
        
        search_custom = graphene.Field(
            self.paginated_object_type, 
            name=f"search{self.name_plural_camel_case}", 
            args={
                **where_arg,
                **order_by_arg,
                **paginated_arg,
                **extra_arg_for_search
            }
        )
        resolve = self.get_fun_resolve_for_search(kwargs)
        return search_custom, resolve


class BuilderCruddalsModel(BuilderCreate, BuilderRead, BuilderUpdate, BuilderDelete, BuilderDeactivate, BuilderActivate, BuilderList, BuilderSearch):
    """
        C = "Create"
        R = "Read"
        U = "Update"
        D = "Delete"
        D = "Deactivate"
        A = "Activate"
        L = "List"
        S = "Search"
    """
    
    model = None
    prefix = None
    suffix = None
    name_snake_case = None
    name_plural_snake_case = None
    name_camel_case = None
    name_plural_camel_case = None
    name_pascal_case = None
    name_plural_pascal_case = None

    model_as_object_type = None
    model_as_input_object_type = None
    paginated_object_type = None
    model_as_form = None

    field_for_read = None
    resolve_field_for_read = None

    field_for_search = None
    resolve_field_for_search = None

    field_for_list = None
    resolve_field_for_list = None

    mutation_create = None
    mutation_update = None
    mutation_activate = None
    mutation_deactivate = None
    mutation_delete = None

    
    def __init__(
            self,
            Model,
            prefix="",
            suffix="",
            interfaces=list(),
            exclude_interfaces=list()) -> None:
        
        assert Model, "Model is required for BuilderCruddalsModel"

        attrs_for_child = [
            "model",
            "prefix",
            "suffix",
            "name_snake_case",
            "name_plural_snake_case",
            "name_camel_case",
            "name_plural_camel_case",
            "name_pascal_case",
            "name_plural_pascal_case",
            "model_as_object_type",
            "model_as_input_object_type",
            "paginated_object_type",
            "model_as_form",
            "field_for_read",
            "resolve_field_for_read",
            "field_for_search",
            "resolve_field_for_search",
            "field_for_list",
            "resolve_field_for_list",
            "mutation_create",
            "mutation_update",
            "mutation_activate",
            "mutation_deactivate",
            "mutation_delete",
        ]
        [setattr(self, attr, None) for attr in attrs_for_child]
        
        names_of_model = get_name_of_model_in_different_case(Model, prefix, suffix)
        self.model = Model
        self.prefix = prefix
        self.suffix = suffix
        self.name_snake_case = names_of_model["snake_case"]
        self.name_plural_snake_case = names_of_model["plural_snake_case"]
        self.name_camel_case = names_of_model["camel_case"]
        self.name_plural_camel_case = names_of_model["plural_camel_case"]
        self.name_pascal_case = names_of_model["pascal_case"]
        self.name_plural_pascal_case = names_of_model["plural_pascal_case"]

        assert isinstance(interfaces, (list,)), f"'interfaces' should be list received {type(interfaces)}"
        
        interfaces_name_cruddals = FINAL_CLASS_NAMES
        dict_of_interface_attr = {interface_name: OrderedDict() for interface_name in interfaces_name_cruddals}
        dict_of_interface_attr['MetaObjectType'] = OrderedDict()
        dict_of_interface_attr['MetaInputObjectType'] = OrderedDict()

        if exclude_interfaces is None:
            exclude_interfaces = []

        for interface in interfaces:
            if interface.__name__ in exclude_interfaces:
                continue
            for interface_name in interfaces_name_cruddals:
                current_interface = getattr(interface, interface_name, None)
                interface_attrs = {}
                
                if current_interface is not None:
                    if interface_name == CruddalsInterfaceNames.OBJECT_TYPE.value:
                        interface_attrs = self.get_interface_attrs(current_interface, False)
                        interface_meta_attrs = self.get_interface_meta_attrs(current_interface)
                        dict_of_interface_attr['MetaObjectType'] = merge_dict(destination=dict_of_interface_attr['MetaObjectType'], source=interface_meta_attrs, keep_both=True)
                    elif interface_name == CruddalsInterfaceNames.INPUT_OBJECT_TYPE.value:
                        interface_attrs = self.get_interface_attrs(current_interface, False)
                        interface_meta_attrs = self.get_interface_meta_attrs(current_interface)
                        dict_of_interface_attr['MetaInputObjectType'] = merge_dict(destination=dict_of_interface_attr['MetaInputObjectType'], source=interface_meta_attrs, keep_both=True)
                    else:
                        interface_attrs = self.get_interface_attrs(current_interface)
                        self.save_pre_post_how_list(interface_attrs)
                        validation_func = getattr(self, f"validate_props_{interface_name.lower()}")
                        validation_func(interface_attrs, interface.__name__)
                
                dict_of_interface_attr[interface_name] = merge_dict(destination=dict_of_interface_attr[interface_name], source=interface_attrs, keep_both=True)

        self.model_as_object_type = convert_model_to_object_type(model=self.model, extra_meta_attrs=dict_of_interface_attr["MetaObjectType"], extra_attrs=dict_of_interface_attr[CruddalsInterfaceNames.OBJECT_TYPE.value], prefix_for_name=prefix, suffix_for_name=suffix)
        self.model_as_input_object_type = convert_model_to_mutation_input_object_type(model=self.model, type_mutation="create_update", meta_attrs=dict_of_interface_attr["MetaInputObjectType"], extra_attrs=dict_of_interface_attr[CruddalsInterfaceNames.INPUT_OBJECT_TYPE.value], prefix_for_name=prefix, suffix_for_name=suffix)        
        self.paginated_object_type = convert_model_to_paginated_object_type(model=self.model, model_as_object_type=self.model_as_object_type, extra_attrs={}, prefix_for_name=prefix, suffix_for_name=suffix)
        self.model_as_form = convert_model_to_model_form(model=self.model, extra_meta_attrs={}, extra_attrs={}, prefix_for_name=prefix, suffix_for_name=suffix)

        builders = {
            'Read': self.build_read,
            'Search': self.build_search,
            'List': self.build_list,
            'Create': self.build_create,
            'Update': self.build_update,
            'Activate': self.build_activate,
            'Deactivate': self.build_deactivate,
            'Delete': self.build_delete
        }

        for prop_name, builder in builders.items():
            built = builder(**dict_of_interface_attr[prop_name])
            if prop_name in ['Read', 'Search', 'List']:
                field_name = f"field_for_{prop_name.lower()}"
                resolve_field_name = f"resolve_{field_name}"
                setattr(self, field_name, built[0])
                setattr(self, resolve_field_name, built[1])
            elif prop_name in ['Create', 'Update', 'Delete', 'Deactivate', 'Activate']:
                mutation_name = f"mutation_{prop_name.lower()}"
                setattr(self, mutation_name, built)


class CruddalsModel(SubclassWithMeta):
    
    Query = None
    Mutation = None
    Schema = None

    queries = None
    mutations = None

    attrs_for_query_read = None
    attrs_for_query_list = None
    attrs_for_query_search = None
    attr_for_mutation_create = None
    attr_for_mutation_update = None
    attr_for_mutation_activate = None
    attr_for_mutation_deactivate = None
    attr_for_mutation_delete = None

    meta = None
    
    @classmethod
    def __init_subclass_with_meta__(
        self,
        model=None,
        prefix="",
        suffix="",
        interfaces=list(),
        exclude_interfaces=list(),
        functions=list(),
        exclude_functions=list(),
        **kwargs
        ):
        
        assert model, "model is required for CruddalsModel"
        validate_list_func_cruddals(functions, exclude_functions)

        attrs_for_child = [
            "Query",
            "Mutation",
            "Schema",
            "queries",
            "mutations",
            "attrs_for_query_read",
            "attrs_for_query_list",
            "attrs_for_query_search",
            "attr_for_mutation_create",
            "attr_for_mutation_update",
            "attr_for_mutation_activate",
            "attr_for_mutation_deactivate",
            "attr_for_mutation_delete",
            "meta"
        ]
        [setattr(self, attr, None) for attr in attrs_for_child]

        cruddals_of_model = BuilderCruddalsModel(
            Model=model,
            prefix=prefix,
            suffix=suffix,
            interfaces=interfaces,
            exclude_interfaces=exclude_interfaces,
        )

        self.meta = cruddals_of_model

        functions_type_query = ['read', 'list', 'search']
        functions_type_mutation = ['create', 'update', 'activate', 'deactivate', 'delete']

        for function in functions_type_query:
            setattr(self, f"attrs_for_query_{function}", {
                f"{function}_{cruddals_of_model.name_plural_snake_case}": getattr(cruddals_of_model, f"field_for_{function}"),
                f"resolve_{function}_{cruddals_of_model.name_plural_snake_case}": getattr(cruddals_of_model, f"resolve_field_for_{function}")
            })
        
        for function in functions_type_mutation:
            setattr(self, f"attr_for_mutation_{function}", {
                f"{function}_{cruddals_of_model.name_plural_snake_case}": getattr(cruddals_of_model, f"mutation_{function}").Field()
            })

        self.queries = {}
        self.mutations = {}
        if functions:
            for function in functions:
                if function in functions_type_query:
                    attrs_for_query = getattr(self, f"attrs_for_query_{function}")
                    self.queries.update(attrs_for_query)
                elif function in functions_type_mutation:
                    attrs_for_query = getattr(self, f"attr_for_mutation_{function}")
                    self.mutations.update(attrs_for_query)
        elif exclude_functions:
            for function in functions_type_query + functions_type_mutation:
                if function not in exclude_functions:
                    if function in functions_type_query:
                        attrs_for_query = getattr(self, f"attrs_for_query_{function}")
                        self.queries.update(attrs_for_query)
                    elif function in functions_type_mutation:
                        attr_for_mutation = getattr(self, f"attr_for_mutation_{function}")
                        self.mutations.update(attr_for_mutation)
        else:
            for function in functions_type_query:
                attrs_for_query = getattr(self, f"attrs_for_query_{function}")
                self.queries.update(attrs_for_query)
            for function in functions_type_mutation:
                attr_for_mutation = getattr(self, f"attr_for_mutation_{function}")
                self.mutations.update(attr_for_mutation)
        
        if not self.queries:
            self.queries.update(self.attrs_for_query_read)

        self.Query = build_class( name='Query', bases=(graphene.ObjectType,), attrs=self.queries )
        
        dict_for_schema = dict(query=self.Query)

        if len(self.mutations.keys()) > 0:
            self.Mutation = build_class( name='Mutation', bases=(graphene.ObjectType,), attrs=self.mutations)
            dict_for_schema.update({"mutation": self.Mutation})
        
        self.Schema = graphene.Schema(**dict_for_schema)

        registry = get_global_registry(f"{prefix}{suffix}")
        registry.register_model(model, "cruddals", self)

        super(CruddalsModel, self).__init_subclass_with_meta__()


class BuilderCruddalsApp:
    
    app_name = None
    app_config = None
    models = None
    cruddals_of_models = dict()

    queries = list()
    mutations = list()

    def __init__(
            self,
            app_name,
            exclude_models=None,
            models=None,
            prefix="",
            suffix="",
            interfaces=list(),
            exclude_interfaces=list(),
            functions=list(),
            exclude_functions=list(),
            settings_for_model=dict()) -> None:
        
        assert app_name, "app_name is required for BuilderCruddalsApp"
        validate_list_func_cruddals(functions, exclude_functions)

        [setattr(self, attr, None) for attr in [ "app_name", "app_config", "models"]]
        setattr(self, 'cruddals_of_models', dict())
        setattr(self, 'queries', list())
        setattr(self, 'mutations', list())

        include_models = models
        assert not (exclude_models and include_models), ( f"Cannot set both 'exclude_models' and 'models' options on {app_name}." )

        interfaces_app = interfaces
        exclude_interfaces_app = exclude_interfaces
        functions_app = functions
        exclude_functions_app = exclude_functions

        assert isinstance(interfaces_app, (list,)), f"'interfaces' should be list received {type(interfaces_app)}"
        assert isinstance(exclude_interfaces_app, (list,)), f"'exclude_interfaces' should be list received {type(exclude_interfaces_app)}"
        assert isinstance(functions_app, (list,)), f"'functions' should be list received {type(functions_app)}"
        assert isinstance(exclude_functions_app, (list,)), f"'exclude_functions' should be list received {type(exclude_functions_app)}"
        assert isinstance(settings_for_model, dict), f"'settings_for_model' should be dict, received {type(settings_for_model)}"

        self.app_name = app_name
        self.app_config = django_apps.get_app_config(app_name)
        self.models = list(self.app_config.get_models())

        if exclude_models is not None:
            assert isinstance(exclude_models, (list,)), f"'exclude_models' should be list received {type(exclude_models)}"
            models_to_exclude = set()
            for exclude_model in exclude_models:
                model_to_exclude = self.app_config.get_model(model_name=exclude_model)
                models_to_exclude.add(model_to_exclude)

            self.models = list(set(self.models) - models_to_exclude)
        elif include_models is not None:
            assert isinstance(include_models, (list,)), f"'models' should be list received {type(include_models)}"
            models_to_include = []
            for include_model in include_models:
                model_to_include = self.app_config.get_model(model_name=include_model)
                models_to_include.append(model_to_include)

            self.models = models_to_include

        for Model in self.models:
            settings_model = settings_for_model.get(Model.__name__, dict())

            settings_model["interfaces"] = interfaces_app + settings_model.get("interfaces", [])
            settings_model["exclude_interfaces"] = exclude_interfaces_app + settings_model.get("exclude_interfaces", [])
            
            settings_model["functions"] = functions_app + settings_model.get("functions", [])
            settings_model["exclude_functions"] = exclude_functions_app + settings_model.get("exclude_functions", [])
            
            settings_model["prefix"] = settings_model.get("prefix", prefix)
            settings_model["suffix"] = settings_model.get("suffix", suffix)

            cruddals_model_meta = build_class(
                name='Meta', 
                attrs={"model": Model, **settings_model}
            )
            cruddals_model = build_class(
                name=f"{Model.__name__}Cruddals", 
                bases=(CruddalsModel,), 
                attrs={"Meta": cruddals_model_meta}
            )

            self.cruddals_of_models.update({
                f"{cruddals_model.meta.name_camel_case}": cruddals_model
            })
            
            self.queries.append(cruddals_model.Query)
            if cruddals_model.Mutation:
                self.mutations.append(cruddals_model.Mutation)


class CruddalsApp(SubclassWithMeta):
    
    Query = None
    Mutation = None
    Schema = None

    meta = None
    
    @classmethod
    def __init_subclass_with_meta__( 
        cls, 
        app_name, 
        
        models=None,
        exclude_models=None,
        
        prefix="",
        suffix="",
        
        interfaces=list(),
        exclude_interfaces=list(),
        
        functions=list(),
        exclude_functions=list(),
        
        settings_for_model=dict()
        ):
        
        assert app_name, "app_name is required for CruddalsApp"
        validate_list_func_cruddals(functions, exclude_functions)

        [setattr(cls, attr, None) for attr in ["Query", "Mutation", "Schema", "meta"]]

        cruddals_of_app = BuilderCruddalsApp(
            app_name=app_name,
            exclude_models=exclude_models,
            models=models,
            prefix=prefix,
            suffix=suffix,
            interfaces=interfaces,
            exclude_interfaces=exclude_interfaces,
            functions=functions,
            exclude_functions=exclude_functions,
            settings_for_model=settings_for_model,
        )

        try:
            base = (graphene.ObjectType,)
            queries_models = tuple(cruddals_of_app.queries) + base
            if cruddals_of_app.mutations:
                mutations_models = tuple(cruddals_of_app.mutations) + base
                cls.Mutation = build_class( name='Mutation', bases=mutations_models)

            cls.meta = cruddals_of_app
            cls.Query = build_class( name='Query', bases=queries_models)

            dict_for_schema = {"query": cls.Query}
            if cls.Mutation:
                dict_for_schema.update({"mutation": cls.Mutation})
            
            cls.Schema = graphene.Schema(**dict_for_schema)
            
            super(CruddalsApp, cls).__init_subclass_with_meta__()
        except Exception as e:
            print("**************ERROR**************")
            print(app_name)
            print(e)
            print("**************ERROR**************")

