# -*- coding: utf-8 -*-
import re

from odoo import SUPERUSER_ID, api, models, tools
from odoo.http import request

# Le cookie `cids` sépare les identifiants par une virgule en 16 ; le tiret
# est accepté par sécurité, c'est le séparateur des versions suivantes.
SEPARATEURS_CIDS = re.compile(r'[,\-]')

# Logical operations that can be forbidden on a model, mapped to the boolean
# field carrying the restriction on ``cpss.access.model.rule``. The first ones
# are real ORM operations, the last ones are interface switches resolved the
# same way.
MODEL_OPERATIONS = {
    'create': 'disable_create',
    'write': 'disable_edit',
    'unlink': 'disable_delete',
    'duplicate': 'disable_duplicate',
    'export': 'disable_export',
    'archive': 'disable_archive',
    'actions': 'disable_actions',
    'print': 'disable_print',
    'chatter': 'hide_chatter',
    'filters': 'hide_filters',
    'group_by': 'hide_group_by',
}

# Record rule modes carried by ``cpss.access.domain.rule``.
DOMAIN_MODES = {
    'read': 'perm_read',
    'write': 'perm_write',
    'create': 'perm_create',
    'unlink': 'perm_unlink',
}

# Rule models contributing to the resolved structure.
RULE_MODELS = (
    'cpss.access.menu.rule',
    'cpss.access.model.rule',
    'cpss.access.field.rule',
    'cpss.access.button.rule',
    'cpss.access.report.rule',
    'cpss.access.domain.rule',
)


class CpssAccessResolver(models.AbstractModel):
    """Single entry point computing the restrictions applying to a user.

    Restrictions come from two places, merged with a "most restrictive wins"
    rule: the access profiles the user belongs to
    (``res.users.access_profile_ids``) and the rule lines targeting the user
    directly (``user_id`` set on a rule record). Nothing ever re-grants what
    another rule forbids.

    Restrictions are resolved for the **active company**, not for the whole
    set of companies the user may reach: a rule carrying a company applies
    only while the user works in that company, so the same user can be
    restricted in one company and free in another.

    Every view load and every ORM access check goes through this resolver, so
    the resolution is cached per user and per company in the registry cache,
    and invalidated by the rule models themselves.
    """
    _name = 'cpss.access.resolver'
    _description = "Access Restriction Resolver"

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    @api.model
    def _get_user_restrictions(self):
        """Return the restrictions applying to the current environment.

        The returned mapping must be treated as read-only: it is shared
        through the registry cache.
        """
        env = self.env
        if env.su or env.uid == SUPERUSER_ID or env.context.get('install_mode'):
            return self._empty_restrictions()
        if not self._has_any_restriction():
            return self._empty_restrictions()
        return self._get_restrictions(env.uid, self._get_active_company_id())

    @api.model
    def _get_active_company_id(self):
        """Société dans laquelle l'utilisateur travaille réellement.

        ``env.company`` ne suffit pas. Les routes HTTP qui chargent le menu
        (``/web/webclient/load_menus/...``) et la page d'accueil ne
        transportent aucun contexte de société : ``env.company`` y retombe sur
        la société **par défaut** de l'utilisateur, pas sur celle qu'il a
        sélectionnée. Une restriction visant une autre société ne se serait
        alors jamais appliquée aux menus.

        L'ordre de résolution suit la fiabilité de chaque source : le contexte
        envoyé par le client, puis le cookie ``cids`` qu'il maintient lui-même
        à chaque basculement, puis la société par défaut.
        """
        company_ids = self.env.context.get('allowed_company_ids')
        if company_ids:
            return company_ids[0]
        company_id = self._get_company_id_from_cookie()
        if company_id and company_id in self.env.user.company_ids.ids:
            return company_id
        return self.env.company.id

    @api.model
    def _get_company_id_from_cookie(self):
        """Premier identifiant du cookie ``cids``, ou ``None`` hors requête."""
        try:
            cids = request.httprequest.cookies.get('cids')
        except Exception:
            # Appel hors contexte HTTP : tâche planifiée, shell, tests.
            return None
        if not cids:
            return None
        try:
            return int(SEPARATEURS_CIDS.split(cids)[0])
        except (TypeError, ValueError):
            return None

    @api.model
    def _is_operation_forbidden(self, model_name, operation):
        """Whether ``operation`` is forbidden on ``model_name`` for this user."""
        restrictions = self._get_user_restrictions()
        return operation in restrictions['models'].get(model_name, ())

    @api.model
    def _get_field_restrictions(self, model_name):
        """Return ``{field_name: frozenset(attributes)}`` for ``model_name``."""
        return self._get_user_restrictions()['fields'].get(model_name, {})

    @api.model
    def _get_domain_restrictions(self, model_name, mode):
        """Return the extra domains to apply on ``model_name`` for ``mode``."""
        return tuple(
            domain
            for domain, modes in self._get_user_restrictions()['domains'].get(
                model_name, ())
            if mode in modes
        )

    @api.model
    def _clear_caches(self):
        """Drop the resolution cache after any change to the rules."""
        self.clear_caches()

    # -------------------------------------------------------------------------
    # RESOLUTION
    # -------------------------------------------------------------------------

    @api.model
    @tools.ormcache()
    def _has_any_restriction(self):
        """Whether anything at all is configured, in a single cached query.

        The hooks of this module sit on the hot path of every request, so an
        installation that configures nothing must cost nothing. One query per
        registry cache lifetime answers that, instead of resolving every rule
        family for every user.
        """
        self.env.flush_all()
        tables = [self.env[model]._table for model in RULE_MODELS]
        tables.append(self.env['cpss.access.profile']._table)
        # Chaque branche est parenthésée : sans cela, le LIMIT porterait sur
        # l'UNION entier et non sur la sous-requête.
        selects = [
            '(SELECT 1 FROM "%s" LIMIT 1)' % table for table in tables
        ]
        selects.append(
            '(SELECT 1 FROM "%s" WHERE access_hide_chatter LIMIT 1)'
            % self.env['res.users']._table)
        # Table names come from the registry, never from user input.
        self.env.cr.execute(
            "SELECT EXISTS (%s)" % " UNION ALL ".join(selects))
        row = self.env.cr.fetchone()
        return bool(row and row[0])

    @api.model
    def _empty_restrictions(self):
        return {
            'menus': frozenset(),
            'models': {},
            'fields': {},
            'buttons': {},
            'reports': frozenset(),
            'domains': {},
            'hide_chatter': False,
        }

    @api.model
    @tools.ormcache('uid', 'company_id')
    def _get_restrictions(self, uid, company_id):
        """Resolve and freeze every restriction applying to ``uid``.

        Cached on the user and the active company: all the inputs (profiles,
        rules, companies) are stored data, never session data.
        """
        # sudo: the resolution reads groups and profiles of an arbitrary user.
        user = self.env['res.users'].browse(uid).sudo().exists()
        if not user or user._is_admin() or user.has_group(
                'cpss_access_management.group_access_manager'):
            # The module's own administrators are never restricted, otherwise
            # they could lock themselves out of the configuration screens.
            return self._empty_restrictions()

        rules = self._get_applicable_rules(user, company_id)
        return {
            'menus': self._resolve_menus(rules['cpss.access.menu.rule']),
            'models': self._resolve_models(rules['cpss.access.model.rule']),
            'fields': self._resolve_fields(rules['cpss.access.field.rule']),
            'buttons': self._resolve_buttons(rules['cpss.access.button.rule']),
            'reports': frozenset(
                rules['cpss.access.report.rule'].mapped('report_id').ids),
            'domains': self._resolve_domains(rules['cpss.access.domain.rule']),
            'hide_chatter': self._resolve_hide_chatter(user, company_id),
        }

    @api.model
    def _get_active_profiles(self, user, company_id):
        """Profiles of ``user`` applying in ``company_id``.

        A profile carrying a company is dormant in every other company.
        """
        return user.sudo().access_profile_ids.filtered(
            lambda profile: profile.active and (
                not profile.company_id or profile.company_id.id == company_id))

    @api.model
    def _get_applicable_rules(self, user, company_id):
        """Read the active rules of every family for ``user``.

        A rule applies when it belongs to one of the user's active profiles or
        targets the user directly, and when it carries either no company or
        the company the user is currently working in.
        """
        # sudo: the resolver runs for any user, who has no read access to the
        # access management models themselves.
        user = user.sudo()
        profile_ids = self._get_active_profiles(user, company_id).ids
        domain = [
            '|', ('profile_id', 'in', profile_ids), ('user_id', '=', user.id),
            ('company_id', 'in', [company_id, False]),
        ]
        return {
            model: self.env[model].sudo().search(domain)
            for model in RULE_MODELS
        }

    @api.model
    def _resolve_menus(self, menu_rules):
        menu_ids = set()
        for rule in menu_rules:
            if rule.include_children:
                # sudo: menus are read to expand the hidden sub-tree.
                menu_ids.update(self.env['ir.ui.menu'].sudo().search(
                    [('id', 'child_of', rule.menu_id.id)]).ids)
            else:
                menu_ids.add(rule.menu_id.id)
        return frozenset(menu_ids)

    @api.model
    def _resolve_models(self, model_rules):
        models_restrictions = {}
        for rule in model_rules:
            operations = {
                operation
                for operation, field_name in MODEL_OPERATIONS.items()
                if rule[field_name]
            }
            if operations:
                model_name = rule.model_name
                models_restrictions[model_name] = frozenset(
                    operations | set(models_restrictions.get(model_name, ())))
        return models_restrictions

    @api.model
    def _resolve_fields(self, field_rules):
        fields_restrictions = {}
        for rule in field_rules:
            model_fields = fields_restrictions.setdefault(rule.model_name, {})
            field_name = rule.field_name
            model_fields[field_name] = frozenset(
                set(model_fields.get(field_name, ())) | {rule.attribute})
        return fields_restrictions

    @api.model
    def _resolve_buttons(self, button_rules):
        buttons_restrictions = {}
        for rule in button_rules:
            model_elements = buttons_restrictions.setdefault(rule.model_name, {})
            model_elements[rule.element_type] = frozenset(
                set(model_elements.get(rule.element_type, ()))
                | {rule.element_name})
        return buttons_restrictions

    @api.model
    def _resolve_domains(self, domain_rules):
        """Return ``{model: ((domain_string, frozenset(modes)), ...)}``.

        The domain is kept as its source string: it is evaluated at access
        time, with the record rule evaluation context, so expressions like
        ``user.id`` stay dynamic.
        """
        domains_restrictions = {}
        for rule in domain_rules:
            modes = frozenset(
                mode for mode, field_name in DOMAIN_MODES.items()
                if rule[field_name]
            )
            if not modes:
                continue
            domains_restrictions.setdefault(rule.model_name, []).append(
                (rule.domain, modes))
        return {
            model_name: tuple(domains)
            for model_name, domains in domains_restrictions.items()
        }

    @api.model
    def _resolve_hide_chatter(self, user, company_id):
        return bool(
            user.access_hide_chatter
            or any(self._get_active_profiles(user, company_id).mapped(
                'hide_chatter'))
        )
