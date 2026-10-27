"""Register OAN components after each native process initializes its services.

Worker and beat retain their native engines and configuration. Registration has
no API initializer, migration, task replacement or scheduler side effects.
"""


def install():
    from .register_domain.services import (
        install_farmer_household_check,
        install_registrant_auth_compat,
    )
    from .register_domain.services.attribute_messages import install_attribute_messages
    from .register_domain.services.outgest_json import install_outgest_json
    from .odk import install as install_odk

    install_registrant_auth_compat()
    install_farmer_household_check()
    install_attribute_messages()
    install_outgest_json()
    install_odk()
