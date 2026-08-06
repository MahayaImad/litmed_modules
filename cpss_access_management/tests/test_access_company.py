# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccessCompany(TransactionCase):
    """A rule carrying a company applies only in that company.

    The point of the feature: the same user can be restricted while working
    in one company and unrestricted in another, without changing anything on
    their account when they switch.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': "Société A"})
        cls.company_b = cls.env['res.company'].create({'name': "Société B"})
        cls.user = cls.env['res.users'].create({
            'name': "Restreint",
            'login': 'restreint_multi',
            'groups_id': [Command.set(cls.env.ref('base.group_user').ids)],
            'company_ids': [Command.set([cls.company_a.id, cls.company_b.id])],
            'company_id': cls.company_a.id,
        })
        cls.partner_model = cls.env.ref('base.model_res_partner')

    def setUp(self):
        super().setUp()
        self.env.registry.clear_caches()
        self.addCleanup(self.env.registry.clear_caches)

    def _restrictions(self, company):
        """Restrictions resolved for the user working in ``company``."""
        env = self.env(user=self.user, context={
            'allowed_company_ids': [company.id],
        })
        return env['cpss.access.resolver']._get_user_restrictions()

    # -------------------------------------------------------------------------
    # RULES
    # -------------------------------------------------------------------------

    def test_01_rule_applies_only_in_its_company(self):
        self.env['cpss.access.model.rule'].create({
            'user_id': self.user.id,
            'company_id': self.company_a.id,
            'model_id': self.partner_model.id,
            'disable_create': True,
        })
        self.assertIn(
            'create', self._restrictions(self.company_a)['models'].get(
                'res.partner', ()),
            "the rule must apply in the company it carries")
        self.assertNotIn(
            'create', self._restrictions(self.company_b)['models'].get(
                'res.partner', ()),
            "the rule must be dormant in every other company")

    def test_02_rule_without_company_applies_everywhere(self):
        self.env['cpss.access.model.rule'].create({
            'user_id': self.user.id,
            'model_id': self.partner_model.id,
            'disable_create': True,
        })
        for company in (self.company_a, self.company_b):
            self.assertIn(
                'create',
                self._restrictions(company)['models'].get('res.partner', ()),
                "a rule without company applies whatever the company")

    def test_03_menu_hidden_in_one_company_only(self):
        action = self.env['ir.actions.act_window'].create({
            'name': "Contacts",
            'res_model': 'res.partner',
            'view_mode': 'tree,form',
        })
        menu = self.env['ir.ui.menu'].create({
            'name': "Contacts A",
            'action': '%s,%s' % (action._name, action.id),
        })
        self.env['cpss.access.menu.rule'].create({
            'user_id': self.user.id,
            'company_id': self.company_a.id,
            'menu_id': menu.id,
        })
        self.assertIn(menu.id, self._restrictions(self.company_a)['menus'])
        self.assertNotIn(menu.id, self._restrictions(self.company_b)['menus'])

    def test_04_profile_is_dormant_outside_its_company(self):
        profile = self.env['cpss.access.profile'].create({
            'name': "Profil Société A",
            'company_id': self.company_a.id,
            'user_ids': [Command.link(self.user.id)],
            'hide_chatter': True,
        })
        self.env['cpss.access.model.rule'].create({
            'profile_id': profile.id,
            'model_id': self.partner_model.id,
            'disable_export': True,
        })
        restrictions_a = self._restrictions(self.company_a)
        self.assertIn('export', restrictions_a['models'].get('res.partner', ()))
        self.assertTrue(restrictions_a['hide_chatter'])

        restrictions_b = self._restrictions(self.company_b)
        self.assertNotIn(
            'export', restrictions_b['models'].get('res.partner', ()),
            "a profile carrying a company must not restrict the other ones")
        self.assertFalse(restrictions_b['hide_chatter'])

    def test_05_cache_is_keyed_on_the_company(self):
        """Resolving for one company must not poison the other."""
        self.env['cpss.access.model.rule'].create({
            'user_id': self.user.id,
            'company_id': self.company_b.id,
            'model_id': self.partner_model.id,
            'disable_edit': True,
        })
        # Company A first: its (empty) result must not be reused for B.
        self.assertNotIn(
            'write', self._restrictions(self.company_a)['models'].get(
                'res.partner', ()))
        self.assertIn(
            'write', self._restrictions(self.company_b)['models'].get(
                'res.partner', ()))


@tagged('post_install', '-at_install')
class TestCompanyNavbarColor(TransactionCase):
    """The colour identifying a company in the navigation bar."""

    def test_01_valid_colours_are_accepted(self):
        company = self.env['res.company'].create({'name': "Couleur"})
        for couleur in ('#017E84', '#abc', '#ABCDEF'):
            company.navbar_color = couleur
            self.assertEqual(company.navbar_color, couleur)

    def test_02_invalid_colour_is_rejected(self):
        company = self.env['res.company'].create({'name': "Couleur"})
        for couleur in ('vert', '#12345', 'rgb(1,2,3)', '017E84'):
            with self.assertRaises(ValidationError):
                company.navbar_color = couleur

    def test_03_empty_colour_is_allowed(self):
        company = self.env['res.company'].create({'name': "Couleur"})
        company.navbar_color = False
        self.assertFalse(company.navbar_color)

    def test_04_default_palette_gives_distinct_colours(self):
        companies = self.env['res.company'].create([
            {'name': "Palette 1"}, {'name': "Palette 2"}, {'name': "Palette 3"},
        ])
        companies.action_cpss_couleur_par_defaut()
        couleurs = companies.mapped('navbar_color')
        self.assertEqual(len(set(couleurs)), 3,
                         "each company must get its own colour")
