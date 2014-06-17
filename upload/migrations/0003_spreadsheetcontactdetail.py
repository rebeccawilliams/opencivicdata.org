# encoding: utf8
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0002_spreadsheetperson'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpreadsheetContactDetail',
            fields=[
                ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True, serialize=False)),
                ('person', models.ForeignKey(to_field='id', to='upload.SpreadsheetPerson')),
                ('type', models.TextField()),
                ('value', models.TextField()),
                ('label', models.TextField()),
                ('note', models.TextField()),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
