# -*- coding: utf-8 -*-
{
    'name': "Access Management",
    'summary': "Restrict menus, models and fields per user from a single screen",
    'description': """
Access Management
=================
Centralises in one application everything a functional administrator needs to
restrict what a user may see and do, without writing a line of XML or Python:
hide menus, forbid create/edit/delete/duplicate/export/archive on a model,
hide the action and print menus, turn any field invisible, read-only,
required or link-less, hide buttons, notebook tabs, the chatter, the filters
and the group by entries, forbid a given report, and narrow the records a
user may reach with a dynamic domain.

Design principles
-----------------
* Two layers, always: the interface is cleaned up for comfort, and the ORM
  raises ``AccessError`` so a direct RPC call is blocked too.
* Restrictions are configured either on a reusable **access profile** shared
  by several users, or directly on a single user. Both are merged with a
  "most restrictive wins" rule.
* Administrators are never restricted, so nobody can lock themselves out of
  the configuration.
* Everything goes through one cached resolver, because view loading and access
  checks are on the hot path of every request.

© 2026 CPSS — https://www.cpss-dz.com
""",
    'author': "CPSS",
    'website': "https://www.cpss-dz.com",
    'category': 'Technical/Access Rights',
    'version': '19.0.1.1.0',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/cpss_access_management_security.xml',
        'security/ir.model.access.csv',
        'views/access_profile_views.xml',
        'views/access_rule_views.xml',
        'views/res_users_views.xml',
        'views/cpss_access_management_menus.xml',
    ],
    'application': True,
    'installable': True,
}
