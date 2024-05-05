from .views.cruddals_views import CRUDDALSView
from .main import CruddalsModel, CruddalsApp
from .utils.utils import *

__version__ = "1.0.0"

__all__ = [
    "__version__",


    # utils
    "is_iterable",
    "django_is_running_with_runserver",
    "get_python_obj_from_string",
    "check_user_has_permission",
    "paginate_queryset",
    "camel_to_snake",
    "snake_to_case",
    "transform_string",
    "delete_keys",
    "merge_dict",
    "build_class",
    "get_class_in_bases",
    "add_cruddals_model_to_request",
    "get_name_of_model_in_different_case",

    #views
    "CRUDDALSView",

    #registries
    "get_global_registry",
    "reset_global_registry",


    #main
    "CruddalsModel",
    "CruddalsApp",

    #TODO: Helpers, interfaces

]






































