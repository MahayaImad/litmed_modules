# Copyright 2025 CPSS
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo import api, fields, models, _


class CpssSyncMixin(models.AbstractModel):
    _name = 'cpss.sync.mixin'
    _description = 'Synchronization Mixin'

    # Champs de synchronisation basiques
    sync_state = fields.Selection([
        ('not_synced', 'Not Synchronized'),
        ('synced', 'Synchronized'),
        ('error', 'Sync Error'),
    ], string="Sync State", default='not_synced', readonly=True)

    sync_error_message = fields.Text(string="Sync Error", readonly=True)
    last_sync_date = fields.Datetime(string="Last Sync Date", readonly=True)

    def _update_sync_state(self, state, error_msg=None):
        """Met à jour l'état de synchronisation"""
        vals = {
            'sync_state': state,
            'last_sync_date': fields.Datetime.now(),
        }
        if error_msg:
            vals['sync_error_message'] = error_msg
        else:
            vals['sync_error_message'] = False

        self.write(vals)