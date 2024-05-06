"""
Settings for TODO
"""
from __future__ import unicode_literals

import six
from django.conf import settings
from django.test.signals import setting_changed

try:
    import importlib  # Available in Python 3.1+
except ImportError:
    from django.utils import importlib  # Will be removed in Django 1.9


DEFAULTS = {
    "APPS": "__all__",
    "EXCLUDE_APPS": [],
    "ACTIVE_INACTIVE_STATE_CONTROLLER_FIELD": "is_active", #TODO: Mejorar esto para que sea mas automático y responsabilidad de cruddals
    "INTERFACES": [],
    "SETTINGS_FOR_APP": {},

    # {
    #     "app_name": {
    
    #         "models": ["model_name", "other_model_name"],
    #         "exclude_models": ["model_name_to_exclude"],

    #         "interfaces": ["app_name.interfaces.Interface1", "app_name.interfaces.Interface2"],
    #         "exclude_interfaces": ["app_name.interfaces.Interface1", "app_name.interfaces.Interface2"],

    #         "functions": ["app_name.interfaces.Interface1", "app_name.interfaces.Interface2"],
    #         "exclude_functions": ["app_name.interfaces.Interface1", "app_name.interfaces.Interface2"],

    #         "settings_for_model": {
    #             "model_name": {
    
    #                 "interfaces": ["app_name.interfaces.Interface3", "app_name.interfaces.Interface4"],
    #                 "exclude_interfaces": ["app_name.interfaces.Interface3", "app_name.interfaces.Interface4"],
    
    #                 "functions": ["read", "create"]
    #                 "exclude_functions": ["read", "create"]
    
    #             }
    #         }
    #     }
    # }
}

# CRUDDALS = {
#     'APPS': [
#         "auth",
#         "core",
#         "accounts",
#         "menu",
#         "orders",
#         "restaurant",
#     ],
#     'INTERFACES': ["dineup.cruddals_interfaces.AuthenticationInterface", "dineup.cruddals_interfaces.ExcludeAuditFields"],
#     'SETTINGS_FOR_APP': {
#         'accounts': {
#             'settings_for_model': {
#                 'DineUpUser': {
#                     'interfaces': ["accounts.cruddals_interfaces.DineUpUserInterface"]
#                 },
#                 'Role': {
#                     'interfaces': ["accounts.cruddals_interfaces.RoleInterface"]
#                 },
#                 'Employee': {
#                     'interfaces': ["accounts.cruddals_interfaces.EmployeeInterface"]
#                 }
#             }
#         },
#         'restaurant': {
#             'settings_for_model': {
#                 'Restaurant': {
#                     'interfaces': ["restaurant.cruddals_interfaces.RestaurantInterface"]
#                 },
#                 'Branch': {
#                     'interfaces': ["restaurant.cruddals_interfaces.BranchInterface"]
#                 },
#                 'Table': {
#                     'interfaces': ["restaurant.cruddals_interfaces.TableInterface"]
#                 },
#             }
#         },
#         'menu': {
#             'settings_for_model': {
#                 'ItemImage': {
#                     'interfaces': ["menu.cruddals_interfaces.ItemImageInterface"]
#                 },
#                 'Menu': {
#                     'interfaces': ["menu.cruddals_interfaces.MenuInterface"]
#                 },
#                 'MenuItem': {
#                     'interfaces': ["menu.cruddals_interfaces.MenuItemInterface"]
#                 },
#                 'Category': {
#                     'interfaces': ["menu.cruddals_interfaces.CategoryInterface"]
#                 }
#             }
#         },
#         'orders': {
#             'settings_for_model': {
#                 'Order': {
#                     'interfaces': ["orders.cruddals_interfaces.OrderInterface"]
#                 },
#             }
#         },
#     }
# }



# List of settings that may be in string import notation.
IMPORT_STRINGS = ("MIDDLEWARE", "SCHEMA")


def perform_import(val, setting_name):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if val is None:
        return None
    elif isinstance(val, six.string_types):
        return import_from_string(val, setting_name)
    elif isinstance(val, (list, tuple)):
        return [import_from_string(item, setting_name) for item in val]
    return val


def import_from_string(val, setting_name):
    """
    Attempt to import a class from a string representation.
    """
    try:
        # Nod to tastypie's use of importlib.
        parts = val.split(".")
        module_path, class_name = ".".join(parts[:-1]), parts[-1]
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        msg = "Could not import '%s' for cruddals setting '%s'. %s: %s." % (
            val,
            setting_name,
            e.__class__.__name__,
            e,
        )
        raise ImportError(msg)


class CruddalsSettings(object):
    """
    A settings object, that allows API settings to be accessed as properties.
    Any setting with string import paths will be automatically resolved
    and return the class, rather than the string literal.
    """

    def __init__(self, user_settings=None, defaults=None, import_strings=None):
        if user_settings:
            self._user_settings = user_settings
        self.defaults = defaults or DEFAULTS
        self.import_strings = import_strings or IMPORT_STRINGS

    @property
    def user_settings(self):
        if not hasattr(self, "_user_settings"):
            self._user_settings = getattr(settings, "CRUDDALS", {})
        return self._user_settings

    def __getattr__(self, attr):
        if attr not in self.defaults:
            raise AttributeError("Invalid cruddals setting: '%s'" % attr)

        try:
            # Check if present in user settings
            val = self.user_settings[attr]
        except KeyError:
            # Fall back to defaults
            val = self.defaults[attr]

        # Coerce import strings into classes
        if attr in self.import_strings:
            val = perform_import(val, attr)

        # Cache the result
        setattr(self, attr, val)
        return val


cruddals_settings = CruddalsSettings(None, DEFAULTS, IMPORT_STRINGS)


def reload_cruddals_settings(*args, **kwargs):
    global cruddals_settings
    setting, value = kwargs["setting"], kwargs["value"]
    if setting == "CRUDDALS":
        cruddals_settings = CruddalsSettings(value, DEFAULTS, IMPORT_STRINGS)


setting_changed.connect(reload_cruddals_settings)
