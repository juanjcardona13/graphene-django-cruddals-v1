from functools import partial

from django.db.models.query import QuerySet


from graphene import NonNull
from graphene.types import Field, List

from cruddals_django.utils.utils import convert_model_to_paginated_object_type, maybe_queryset, order_by_input_to_args, paginate_queryset, where_input_to_Q



class DjangoListField(Field):
    
    def __init__(self, _type, *args, **kwargs):
        from .types import DjangoObjectType

        if isinstance(_type, NonNull):
            _type = _type.of_type

        # Django would never return a Set of None  vvvvvvv
        super().__init__(List(NonNull(_type)), *args, **kwargs)

        assert issubclass( self._underlying_type, DjangoObjectType ), "DjangoListField only accepts DjangoObjectType types"

    @property
    def _underlying_type(self):
        _type = self._type
        while hasattr(_type, "of_type"):
            _type = _type.of_type
        return _type

    @property
    def model(self):
        return self._underlying_type._meta.model

    def get_manager(self):
        return self.model._default_manager

    @staticmethod
    def list_resolver( django_object_type, resolver, default_manager, root, info, **args ):
        queryset = maybe_queryset(resolver(root, info, **args))
        if queryset is None:
            queryset = maybe_queryset(default_manager)

        if isinstance(queryset, QuerySet):
            # Pass queryset to the DjangoObjectType get_queryset method
            queryset = maybe_queryset(django_object_type.get_queryset(queryset, info))

        return queryset

    def wrap_resolve(self, parent_resolver):
        resolver = super().wrap_resolve(parent_resolver)
        _type = self.type
        if isinstance(_type, NonNull):
            _type = _type.of_type
        django_object_type = _type.of_type.of_type
        return partial( self.list_resolver, django_object_type, resolver, self.get_manager(), )


class DjangoPaginatedField(Field):
    
    def __init__(self, _type, *args, **kwargs):
        from .types import DjangoObjectType


        if isinstance(_type, NonNull):
            _type = _type.of_type

        paginate_type = convert_model_to_paginated_object_type(model=_type._meta.model, model_as_object_type=_type)
        # Django would never return a Set of None
        super().__init__(paginate_type, *args, **kwargs)
        
        # assert issubclass( self._underlying_type, DjangoObjectType ), "DjangoPaginatedField only accepts DjangoObjectType types"

    @property
    def _underlying_type(self):
        _type = self._type
        # while hasattr(_type, "of_type"):
        #     _type = _type.of_type
        return _type.objects._underlying_type #TODO-objects

    @property
    def model(self):
        return self._underlying_type._meta.model

    def get_manager(self):
        return self.model._default_manager

    @staticmethod
    def resolver_for_paginated_field( paginated_object_type, django_object_type, resolver, default_manager, root, info, **args ):
        
        maybe_manager = resolver(root, info, **args)
        attname, default_value = resolver.args
        if attname.startswith("paginated_"):
            posible_field = attname.replace("paginated_", "", 1)
            if hasattr(root, posible_field):
                maybe_manager = getattr(root, posible_field, default_value)

        queryset:QuerySet = maybe_queryset(maybe_manager)

        if queryset is None:
            queryset = maybe_queryset(default_manager)

        if isinstance(queryset, QuerySet):
            # Pass queryset to the DjangoObjectType get_queryset method
            queryset = maybe_queryset(django_object_type.get_queryset(queryset, info))
            
        if "where" in args:
            where = args["where"] 
            obj_q = where_input_to_Q(where)
            queryset = queryset.filter(obj_q)
        
        if "order_by" in args or "orderBy" in args:
            order_by = args.get("order_by") or args.get("orderBy")
            if isinstance(order_by, dict):
                order_by = [order_by]
            list_for_order = order_by_input_to_args(order_by)
            queryset = queryset.order_by(*list_for_order)
        else:
            queryset = queryset.order_by("pk")

        paginated = args.get("paginated", {})
        queryset = queryset.distinct()

        return paginate_queryset(queryset, paginated.get('page_size', 'All'), paginated.get('page', 1), paginated_object_type)

    def wrap_resolve(self, parent_resolver):

        resolver = super().wrap_resolve(parent_resolver)

        _type = self.type

        if isinstance(_type, NonNull):
            _type = _type.of_type

        django_object_type = _type.objects._underlying_type #TODO-objects

        return partial( self.resolver_for_paginated_field, _type, django_object_type, resolver, self.get_manager(), )


