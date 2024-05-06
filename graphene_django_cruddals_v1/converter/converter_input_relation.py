from functools import singledispatch


from django.db import models
from django.db.models.fields import Field as DjangoField
from django.utils.functional import Promise

import graphene

from graphql.pyutils import register_description

from graphene_django_cruddals_v1.registry.registry_global import RegistryGlobal
from graphene_django_cruddals_v1.helpers.helpers import TypesMutation



@singledispatch
def convert_relation_field_to_input(field:DjangoField, registry:RegistryGlobal=None, type_mutation_input:TypesMutation=TypesMutation.CREATE.value):
    raise Exception(
        "Don't know how to convert the Django field {} ({}), please check if is relation Field".format(
            field, field.__class__
        )
    )


@convert_relation_field_to_input.register(models.ManyToManyField)
@convert_relation_field_to_input.register(models.ManyToManyRel)
@convert_relation_field_to_input.register(models.ManyToOneRel)
def convert_field_to_list(field:DjangoField, registry:RegistryGlobal=None, type_mutation_input:TypesMutation=TypesMutation.CREATE.value):
    model = field.related_model
    def dynamic_type():

        model_input_object_type = None
        registries_for_model = registry.get_registry_for_model(model)
        if registries_for_model is not None and "input_object_type" in registries_for_model:
            model_input_object_type = registries_for_model["input_object_type"]
        
        if not model_input_object_type:
            return
        

        if type_mutation_input == TypesMutation.CREATE.value:
            return graphene.InputField( graphene.List( model_input_object_type ) )
        
        else: # update, create_update
            
            from graphene_django_cruddals_v1.utils.utils import build_class
            model_where_input_object_type = None
            if registries_for_model is not None and "input_object_type_for_filter" in registries_for_model:
                model_where_input_object_type = registries_for_model["input_object_type_for_filter"]
            if not model_where_input_object_type:
                return        
            
            connect_disconnect_model_input = build_class(
                name=f"{model.__name__}ConnectDisconnectInput",
                bases=(graphene.InputObjectType,),
                attrs={
                    "connect": graphene.List(graphene.NonNull(model_input_object_type)),
                    "disconnect": graphene.List(graphene.NonNull(model_where_input_object_type))
                }
            )

            registry.register_model(model, "input_object_type_for_connect_disconnect", connect_disconnect_model_input)

            return graphene.InputField( connect_disconnect_model_input )
    return graphene.Dynamic(dynamic_type)



@convert_relation_field_to_input.register(models.OneToOneField)
@convert_relation_field_to_input.register(models.ForeignKey)
@convert_relation_field_to_input.register(models.OneToOneRel)
def convert_field_to_input_django_model(field:DjangoField, registry:RegistryGlobal=None, type_mutation_input:TypesMutation=TypesMutation.CREATE.value):
    model = field.related_model
    
    def dynamic_type():
        model_input_object_type = None
        registries_for_model = registry.get_registry_for_model(model)
        if registries_for_model is not None and "input_object_type" in registries_for_model:
            model_input_object_type = registries_for_model["input_object_type"]
        if not model_input_object_type:
            return
        
        # Avoid create field for auto generate OneToOneField product of an inheritance
        if isinstance(field, models.OneToOneField) and issubclass( field.model, field.related_model ):
            return
        
        return graphene.InputField( model_input_object_type )
    return graphene.Dynamic(dynamic_type)





register_description(Promise)
