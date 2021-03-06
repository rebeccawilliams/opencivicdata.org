import re
import csv
from .xlrd import xlrd_dict_reader
from .csv import csv_dict_reader
from ..models import (SpreadsheetUpload, SpreadsheetPerson,
                      SpreadsheetMembership, SpreadsheetUploadSource,
                      SpreadsheetPersonSource, SpreadsheetLink,
                      SpreadsheetContactDetail)

from collections import defaultdict
from contextlib import contextmanager
from pupa.scrape.popolo import Organization, Person, Post
from opencivicdata.models import Jurisdiction as DBJurisdiction


def people_to_pupa(stream, transaction):
    jurisdiction = DBJurisdiction.objects.get(id=transaction.jurisdiction.id)
    division_id = jurisdiction.division_id

    org = Organization(
        name=transaction.jurisdiction.name,
        classification='legislature',
    )

    for source in list(transaction.sources.all()):
        org.add_source(url=source.url, note=source.note)

    parties = defaultdict(list)
    posts = {}

    for person in stream:
        name = person.name
        image = person.image

        if not name:
            raise ValueError("A name is required for each entry.")

        if name.lower() == "vacant":
            # The following is so that we can create a post without a person
            # attached to it, for vacant seats. Since all that we do
            # below is create the Person, we can get away with just creating
            # the post, without actually filling out the person.
            posts[position] = org
            continue

        start_date, end_date = (x if x else ""
                                for x in (person.start_date, person.end_date))

        people = {}

        if name in people:
            obj = people[name]
        else:
            obj = Person(name=name)
            people[name] = obj

        pcache = {}
        post = Post(label='member', role='member',
                    organization_id=org._id,
                    division_id=division_id)
        org._related.append(post)
        pcache[None] = post._id

        for post, org in posts.items():
            post_obj = org.add_post(
                label=post,
                role=post,
                division_id=division_id,
            )
            pcache[post] = post_obj._id

        for membership in person.memberships.all():
            role = membership.role   # TOWN OF FOO CLERK (F00)
            district = membership.district   # Town of Foo

            obj.add_membership(
                organization=org,
                label=role,
                role=role,
                post_id=pcache.get(role, pcache[None]),
                start_date=start_date,
                end_date=end_date,
            )
            posts[role] = org

        if person.party:
            obj._party = person.party
            parties[person.party].append(person.sources.all())

        if image:
            obj.image = image

        for detail in person.contacts.all():
            obj.add_contact_detail(
                type=detail.type,
                value=detail.value,
                # label=detail.label,  # Unexpected argument. Add?
                note=detail.note,
            )

        for link in person.links.all():
            obj.add_link(
                url=link.url,
                note=link.note,
            )

        for source in (list(person.sources.all())
                       + list(transaction.sources.all())):
            obj.add_source(
                url=source.url,
                note=source.note,
            )

        obj.validate()
        obj.pre_save(transaction.jurisdiction.id)
        yield obj
        for related in obj._related:
            yield related

    for party in dict(parties):
        party = Organization(classification='party', name=party)
        sources = list(parties[party]) + list(transaction.sources.all())

        for source in sources:
            party.add_source(url=source.url, note=source.note)

        party.validate()
        party.pre_save(transaction.jurisdiction.id)
        for related in party._related:
            yield related
        yield party

    org.validate()
    org.pre_save(transaction.jurisdiction.id)
    for related in org._related:
        yield related
    yield org


def iteritems(person):
    ignore = ["employer",]   # XXX: What to do there?
    for key, value in person.copy().items():
        if not value:
            # 'errything is optional.
            continue

        root = key
        label = None

        if "(" in key:
            root, label = key.rsplit("(", 1)
            root = root.strip()
            label = label.rstrip(")").strip()

        root = root.strip().replace(" ", "")
        if root in ignore:
            continue

        yield (key, root, label, value)


def import_parsed_stream(stream, user, jurisdiction, sources):
    upload = SpreadsheetUpload(user=user, jurisdiction=jurisdiction)
    upload.save()

    for source in sources:
        a = SpreadsheetUploadSource(
            upload=upload,
            url=source,
            note="Default Spreadsheet Source"
        )
        a.save()


    for person in stream:
        if not person['name']:
            raise ValueError("Bad district or name")

        memberships = defaultdict(dict)
        vital_data = ['position', 'district']
        for key, root, label, value in iteritems(person):
            if root not in vital_data:
                continue

            person.pop(key)

            if label in memberships[root]:
                raise ValueError("Two '%s' with the same label '%s'" % (
                    root, label
                ))
            memberships[root][label] = value

        if memberships['district'] == {}:
            raise ValueError("No roles found.")

        who = SpreadsheetPerson(
            name=person.pop('name'),
            spreadsheet=upload,
        )

        if 'first name' in person:
            who.given_name = person.pop('first name')

        if 'last name' in person:
            who.family_name = person.pop('last name')

        if 'middle name' in person:
            who.additional_name = person.pop('middle name')

        if 'start date' in person:
            who.start_date = person.pop('start date')

        if 'end date' in person:
            who.end_date = person.pop('end date')

        if 'photo' in person:
            who.image = person.pop("photo")

        if 'image' in person:
            who.image = person.pop("image")

        if 'party' in person:
            who.party = person.pop("party")

        who.save()

        for index in memberships['district']:
            position = memberships['position'].get(index)
            district = memberships['district'][index]
            if position is None:
                position = 'member'

            who.memberships.create(
                district=district,
                role=position
            )

        contact_details = {
            "address": "address",
            "phone": "voice",
            "email": "email",
            "fax": "fax",
            "cell": "voice",
        }

        links = ["website", "homepage",
                 "twitter", "facebook",
                 "google+", "instagram",
                 "linkedin", "flickr",
                 "youtube", "blog",
                 "pinterest", "webform"]

        sources = ["source"]

        for key, root, label, value in iteritems(person):
            if root in sources:
                a = SpreadsheetPersonSource(
                    person=who,
                    url=value,
                    note="",
                )
                a.save()
                continue

            # If we've got a link.
            if root in links:
                a = SpreadsheetLink(
                    person=who,
                    url=value,
                    note="",
                )
                a.save()
                continue

            # If we've got a contact detail.
            if root in contact_details:
                type_ = contact_details[root]
                a = SpreadsheetContactDetail(
                    person=who,
                    type=type_,
                    value=value,
                    label=label or "",
                    note="",
                )
                a.save()
                continue

            raise ValueError("Unknown spreadhseet key: %s" % (key))

    return upload


def import_stream(stream, extension, user, jurisdiction, sources):
    reader = {"csv": csv_dict_reader,
              "xlsx": xlrd_dict_reader,
              "xls": xlrd_dict_reader}[extension]

    return import_parsed_stream(reader(stream), user, jurisdiction, sources)


@contextmanager
def import_file_stream(fpath, user, jurisdiction, sources):
    _, xtn = fpath.rsplit(".", 1)

    with open(fpath, 'br') as fd:
        yield import_stream(fd, xtn, user, jurisdiction, sources)
