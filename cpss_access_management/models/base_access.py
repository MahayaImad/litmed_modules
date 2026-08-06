# -*- coding: utf-8 -*-
import ast
import json

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError

# Root arch attributes turned off per view type when an operation is forbidden.
ROOT_OPERATION_ATTRIBUTES = {
    'tree': {'create': 'create', 'write': 'edit', 'unlink': 'delete',
             'export': 'export_xlsx'},
    'form': {'create': 'create', 'write': 'edit', 'unlink': 'delete',
             'duplicate': 'duplicate'},
    'kanban': {'create': 'create', 'write': 'edit', 'unlink': 'delete'},
}

# Human readable operation names used in the error messages. They are
# translated at raise time and carried by the module's own .po files.
OPERATION_LABELS = {
    'create': "create",
    'write': "modify",
    'unlink': "delete",
    'duplicate': "duplicate",
    'export': "export",
    'archive': "archive",
    'print': "print",
}


class Base(models.AbstractModel):
    """Applies the resolved access restrictions to every model.

    Two layers are applied on purpose:

    * the interface layer (``get_view``, ``fields_get``) removes the buttons
      and fields the user must not use — this is comfort, not security;
    * the ORM layer (``check_access_rights``, ``write``, ``copy``,
      ``export_data``) raises ``AccessError``, which is what actually protects
      the data against a direct RPC call.

    Every hook starts with a cached dictionary lookup and returns immediately
    when the user carries no restriction, which is the case for the vast
    majority of the requests.
    """
    _inherit = 'base'

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    @api.model
    def _cpss_forbidden_operations(self):
        """Return the operations forbidden on this model for the current user."""
        return self.env['cpss.access.resolver']._get_user_restrictions()[
            'models'].get(self._name, frozenset())

    @api.model
    def _cpss_field_restrictions(self):
        """Return ``{field_name: frozenset(attributes)}`` for this model."""
        return self.env['cpss.access.resolver']._get_field_restrictions(self._name)

    @api.model
    def _cpss_raise_forbidden(self, operation):
        raise AccessError(_(
            "Your access profile does not allow you to %(operation)s records "
            "of type %(model)s."
        ) % {
            'operation': _(OPERATION_LABELS.get(operation, operation)),
            'model': self._description or self._name,
        })

    # -------------------------------------------------------------------------
    # ORM ENFORCEMENT
    # -------------------------------------------------------------------------

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        """Odoo 16 splits the check in ``check_access_rights`` (model level)
        and ``check_access_rule`` (record level). The model level is the one
        create/read/write/unlink always go through.
        """
        result = super().check_access_rights(
            operation, raise_exception=raise_exception)
        if operation in self._cpss_forbidden_operations():
            if raise_exception:
                self._cpss_raise_forbidden(operation)
            return False
        return result

    def write(self, vals):
        self._cpss_check_write(vals)
        return super().write(vals)

    def copy(self, default=None):
        if 'duplicate' in self._cpss_forbidden_operations():
            self._cpss_raise_forbidden('duplicate')
        return super().copy(default=default)

    def export_data(self, fields_to_export):
        if 'export' in self._cpss_forbidden_operations():
            self._cpss_raise_forbidden('export')
        return super().export_data(fields_to_export)

    def _cpss_check_write(self, vals):
        """Block archiving and writes on fields forced to read-only."""
        restrictions = self.env['cpss.access.resolver']._get_user_restrictions()
        if not restrictions['models'] and not restrictions['fields']:
            return
        if 'active' in vals and 'archive' in restrictions['models'].get(
                self._name, ()):
            self._cpss_raise_forbidden('archive')
        readonly_fields = {
            field_name
            for field_name, attributes in restrictions['fields'].get(
                self._name, {}).items()
            if 'readonly' in attributes or 'invisible' in attributes
        }
        forbidden = readonly_fields.intersection(vals)
        if forbidden:
            raise AccessError(_(
                "Your access profile does not allow you to modify the "
                "following fields of %(model)s: %(fields)s."
            ) % {
                'model': self._description or self._name,
                'fields': ", ".join(sorted(forbidden)),
            })

    # -------------------------------------------------------------------------
    # INTERFACE
    # -------------------------------------------------------------------------

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields, attributes)
        for field_name, rule_attributes in self._cpss_field_restrictions().items():
            description = result.get(field_name)
            if not description:
                continue
            if 'readonly' in rule_attributes and (
                    not attributes or 'readonly' in attributes):
                description['readonly'] = True
            if 'required' in rule_attributes and (
                    not attributes or 'required' in attributes):
                description['required'] = True
        return result

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        restrictions = self.env['cpss.access.resolver']._get_user_restrictions()
        if not any((restrictions['models'], restrictions['fields'],
                    restrictions['buttons'], restrictions['hide_chatter'])):
            return result
        # The arch is postprocessed here and never in ``_get_view``, whose
        # result is shared between users through the view cache.
        arch = etree.fromstring(result['arch'])
        self._cpss_restrict_arch(arch, self._name, restrictions)
        result['arch'] = etree.tostring(arch, encoding='unicode')
        return result

    @api.model
    def _cpss_restrict_arch(self, node, model_name, restrictions):
        """Apply the restrictions of ``model_name`` to a view root node."""
        operations = restrictions['models'].get(model_name, ())
        self._cpss_apply_root_attributes(node, operations)
        self._cpss_apply_element_rules(
            node, restrictions['buttons'].get(model_name, {}))
        if node.tag == 'form' and (
                restrictions['hide_chatter'] or 'chatter' in operations):
            self._cpss_remove_chatter(node)
        if node.tag == 'search':
            self._cpss_apply_search_rules(node, operations)
        self._cpss_apply_field_attributes(
            node, model_name, node.tag, restrictions)

    # -------------------------------------------------------------------------
    # ARCH HELPERS
    # -------------------------------------------------------------------------

    @api.model
    def _cpss_set_modifier(self, node, name, value=True):
        """Set a modifier on an already postprocessed node.

        ``get_view`` returns the arch *after* Odoo turned ``attrs`` and the
        static ``invisible`` / ``readonly`` / ``required`` attributes into the
        ``modifiers`` JSON blob the web client actually reads. Setting only
        the plain attribute at this stage would have no effect, so the blob is
        edited — the attribute is kept in sync for readability and for any
        code re-parsing the arch.
        """
        try:
            modifiers = json.loads(node.get('modifiers') or '{}')
        except ValueError:
            modifiers = {}
        modifiers[name] = value
        node.set('modifiers', json.dumps(modifiers))
        if value is True:
            node.set(name, '1')

    @api.model
    def _cpss_apply_element_rules(self, node, element_rules):
        """Hide the restricted buttons, notebook pages and named links.

        A page is matched on its ``name`` or, when it has none, on its label,
        because many core views only give their pages a ``string``.
        """
        if not element_rules:
            return
        for tag, element_type in (('button', 'button'), ('page', 'page'),
                                  ('a', 'link')):
            names = element_rules.get(element_type)
            if not names:
                continue
            for element in node.iter(tag):
                if element.get('name') in names or (
                        element_type == 'page'
                        and not element.get('name')
                        and element.get('string') in names):
                    self._cpss_set_modifier(element, 'invisible')

    @api.model
    def _cpss_remove_chatter(self, node):
        """Remove the chatter block from a form arch.

        Odoo 16 has no ``<chatter>`` tag: the chatter is the ``div.oe_chatter``
        sitting after the sheet.
        """
        for chatter in node.xpath(
                ".//div[contains(concat(' ', normalize-space(@class), ' '),"
                " ' oe_chatter ')]"):
            chatter.getparent().remove(chatter)

    @api.model
    def _cpss_apply_search_rules(self, node, operations):
        """Drop the predefined filters and/or group by entries.

        A ``<filter>`` carrying a ``group_by`` context is a group by entry,
        everything else is a filter.
        """
        hide_filters = 'filters' in operations
        hide_group_by = 'group_by' in operations
        if not hide_filters and not hide_group_by:
            return
        for element in list(node.iter('filter')):
            is_group_by = 'group_by' in (element.get('context') or '')
            if (is_group_by and hide_group_by) or (
                    not is_group_by and hide_filters):
                element.getparent().remove(element)
        if hide_group_by:
            for group in list(node.iter('group')):
                if not len(group):
                    group.getparent().remove(group)

    @api.model
    def _cpss_apply_root_attributes(self, node, operations):
        """Turn off the create/edit/delete/duplicate/export root attributes."""
        for operation, attribute in ROOT_OPERATION_ATTRIBUTES.get(
                node.tag, {}).items():
            if operation in operations:
                node.set(attribute, 'false')

    @api.model
    def _cpss_apply_field_attributes(self, node, model_name, view_type,
                                     restrictions):
        """Inject the field attributes, sub-view by sub-view.

        The children of a ``<field>`` node are an inline sub-view of the
        comodel, so the walk switches to the restrictions of that comodel
        instead of blindly reusing the ones of the parent model.
        """
        field_restrictions = restrictions['fields'].get(model_name, {})
        model = self.env[model_name] if model_name in self.env else None
        # Materialised: a hidden search field is removed from its parent.
        for child in list(node):
            if child.tag != 'field':
                self._cpss_apply_field_attributes(
                    child, model_name, view_type, restrictions)
                continue
            field_name = child.get('name')
            attributes = field_restrictions.get(field_name)
            if attributes:
                self._cpss_set_field_attributes(child, attributes, view_type)
                if child.getparent() is None:
                    continue
            field = model._fields.get(field_name) if model is not None else None
            comodel_name = field.comodel_name if field else None
            if comodel_name and len(child):
                for sub_root in child:
                    self._cpss_restrict_arch(sub_root, comodel_name, restrictions)

    @api.model
    def _cpss_set_field_attributes(self, node, attributes, view_type):
        if 'invisible' in attributes:
            if view_type == 'search':
                # A search field cannot be made invisible: drop it, else the
                # user could still filter on a hidden field.
                node.getparent().remove(node)
                return
            self._cpss_set_modifier(node, 'invisible')
            if view_type == 'tree':
                self._cpss_set_modifier(node, 'column_invisible')
            return
        if 'readonly' in attributes:
            self._cpss_set_modifier(node, 'readonly')
        if 'required' in attributes:
            self._cpss_set_modifier(node, 'required')
        if 'no_open' in attributes:
            node.set('options', json.dumps(
                {**self._cpss_node_options(node), 'no_open': True}))

    @api.model
    def _cpss_node_options(self, node):
        try:
            return ast.literal_eval(node.get('options') or '{}')
        except (SyntaxError, ValueError):
            return {}
