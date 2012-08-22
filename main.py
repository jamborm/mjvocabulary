# mjvocabulary - Simple Google AppEngine based vocabulary tester
# Copyright (C) 2012 Martin Jambor
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import jinja2
import os
import cgi
import urllib
import webapp2
import random
import csv
import urllib2
import logging

from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.runtime import apiproxy_errors

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

error_mapping = {
    0 : "No error, this message should not have been displayed :-p",
    1 : "Sorry, bad input",
    2 : "Oops, no or bad test set id",
    3 : "Oops, could not locate the word according to ids",
    4 : "Could not perform all requested deletions",
    5 : "Google appengine free quota depleted.  Come back tomorrow :-(",
    6 : "Generic error accessing the datastore"
    }

class TestSet(db.Model):
    """Models a test set with a name and stuff"""
    owner = db.UserProperty(auto_current_user_add=True)
    name = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)
    pass

class TestWord(db.Model):
    """Model of an actual word to be tested."""
    word = db.StringProperty()
    desc = db.StringProperty(multiline=True)
    good = db.IntegerProperty()
    bad = db.IntegerProperty()
    test = db.BooleanProperty()
    pass

class AllowedUser(db.Model):
    """Model of an actual word to be tested."""
    email = db.StringProperty()
    desc = db.StringProperty()
    pass

class CommonPage(webapp2.RequestHandler):
    """Class with stuff common to all our pages."""

    items_per_page = 30

    def display_login_page (self, extra_info="", simple_back=False):
        """Check if the user is logged in and if not tell him to login."""

        if simple_back:
            url = "/"
        else:
            url = self.request.uri
            pass

        template_values = {
            'extra_info' : extra_info,
            'url': users.create_login_url(url)
            }
        template = jinja_environment.get_template('login.html')
        self.response.out.write(template.render(template_values))
        return

    def get_extra_info_string (self):
        """Return extra info string, usually an error, if there is one"""

        extra_info = ""
        try:
            extra_parm = int(self.request.get("extra", default_value=0))
            if extra_parm > 0 and extra_parm < len(error_mapping):
                extra_info = error_mapping[int(extra_parm)]
        except:
            pass
        return extra_info

    def get_view_index(self):
        """Get the index of te first item to display"""
        try:
           view_index = self.request.get("idx", default_value=0)
           view_index = (int(view_index)/self.items_per_page)*self.items_per_page
        except:
            view_index = 0;
            pass
        return view_index

    def build_link(self, usr, page_url, params):
        """Build a link from page url and any number of parameters

        Parameters are tuples, first item is the parameter name,
        second is the value."""

        l = "<a href=\""+ page_url + "?"
        first = True
        for p in params:
            if not first:
                l = l + "&amp;"
                pass
            l = l + p[0] + "=" + str(p[1])
            first = False
            pass
        l = l + "\">" + usr + "</a>"
        return l


    def get_navig_str (self, backlink, params, view_index, last):
        """Produce a navigation string"""

        if view_index > 0:
            p = view_index - self.items_per_page
            navig = ("|"
                     + self.build_link ("first", backlink,
                                            params + [("idx", 0)])
                     + "|"
                     + self.build_link ("prev", backlink,
                                        params + [("idx", p)])
                     + "|")
        else:
            if last:
                return ""
            navig = "|first|prev|"
            pass

        if not last:
            n = view_index + self.items_per_page
            navig = navig + self.build_link ("next", backlink,
                                             params + [("idx", n)]) + "|"
        else:
            navig = navig + "next|"
            pass
        return navig

    def is_allowed_user(self):
        if users.is_current_user_admin():
            return True
        try:
            q = AllowedUser.all()
            q.filter("email =", users.get_current_user().email().lower())
            result = q.get(keys_only=True)
            if result != None:
                return True
        except apiproxy_errors.OverQuotaError:
            raise
        except:
            pass
        return False
        
    def check_user(self):
        try:
            if (not users.get_current_user()
                or not self.is_allowed_user()):
                self.redirect('/');
                return False
        except:
            self.redirect('/');
            return False
        return True

    def reset_common_values (self):
        self._tsid = None
        self._tsk = None
        self._tset = None
        self._wid = None
        self._wkey = None
        self._word = None
        return

    def do_get_test_set(self):
        tsid = self.request.get("tsid").strip()
        if (tsid == ""):
            return False
        tsid = int(tsid)
        tsk = db.Key.from_path("TestSet", tsid)
        tset = db.get(tsk)
        if (tset == False
            or (tset.owner != users.get_current_user()
                and not users.is_current_user_admin())):
            return False

        self._tsid = tsid
        self._tsk = tsk
        self._tset = tset
        return True

    def get_test_set(self):
        """Get task set id, key and the set based on the id req parameter

        Return true if successful, false if not.  In case of success,
        store data into _tsid, _tsk and _tset variables of the current
        class.  In case of failure, rediect to appropriate page and
        return False."""

        try:
            r = self.do_get_test_set()
            if not r:
                self.redirect("/?extra=2")
                return False
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return False
        except:
            self.redirect("/?extra=2")
            return False
        return True

    def do_get_test_set_and_word_key(self):
        if not self.do_get_test_set():
            return False

        wid = self.request.get("wid").strip()
        if wid == "":
            return False

        wid = int(wid)
        wkey = db.Key.from_path("TestSet", self._tsid, "TestWord", wid)
        self._wid = wid
        self._wkey = wkey
        return True

    def get_test_set_and_word_key(self):
        """In addition to get_test_set also get word id and key

        but not the word itself.  Store stuff to _wid and _wkey.  In
        case of failure, rediect to appropriate page and return
        False."""

        try:
            r = self.do_get_test_set_and_word_key()
            if not r:
                self.redirect('/?extra=3')
                return False
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return False
        except:
            self.redirect('/?extra=3')
            return False
        return True

    def do_get_test_set_and_word(self):

        if not self.do_get_test_set_and_word_key():
            return False

        self._word = db.get(self._wkey)
        if self._word == None:
            return False
        return True

    def get_test_set_and_word(self):
        """In addition to get_test_set also get word, its id and its key

        Store stuff to _wid, _wkey and _word.  In case of failure,
        rediect to appropriate page and return False."""

        try:
            r = self.do_get_test_set_and_word()
            if not r:
                self.redirect('/?extra=3')
                return False
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return False
        except:
            self.redirect('/?extra=3')
            return False
        return True
    pass

class MainPage(CommonPage):
    """The main page"""

    def get(self):
        """Display the main page with test-set listing and manipulation."""

        if not users.get_current_user():
            self.display_login_page()
            return

        extra_info = ""
        try:
            allowed_user = self.is_allowed_user()
        except apiproxy_errors.OverQuotaError:
            extra_info = ("Google appengine datastore free quota depleted, "
                          + "whitelist is thus not accessible. "
                          + "Come back tomorrow :-(")
            allowed_user = False
            pass
        if not allowed_user:
            template_values = {
                "extra_info" : extra_info,
                "logout_url" : users.create_logout_url("/")
                }
            logging.info("Acces by not allowed user %s"
                         % users.get_current_user().email())
            template = jinja_environment.get_template("not_allowed.html")
            self.response.out.write(template.render(template_values))
            return

        self.reset_common_values()
        extra_info = self.get_extra_info_string()
        extra_info_2 = ""
        view_index = self.get_view_index()

        if (self.request.get("all") == "1"
            and users.is_current_user_admin()):
            display_all_users = True
            extra_info_2 = "Displaying sets of all users"
        else:
            display_all_users = False

        result = []
        try:
            q = TestSet.all()
            if not display_all_users:
                q.filter("owner = ", users.get_current_user());
            q.order("-date")
            result = q.fetch(limit = self.items_per_page + 1,
                             offset = view_index);
        except apiproxy_errors.OverQuotaError:
            extra_info_2 = error_mapping[5]
            pass
        except:
            extra_info_2 = error_mapping[6]
            pass

        if (len(result) > self.items_per_page):
            last = False
            result = result[:-1]
        else:
            last = True
            pass

        rlist = [ {"name" : r.name,
                   "date" : "%i-%.2i-%.2i" %(r.date.year,
                                             r.date.month, r.date.day),
                   "id" : r.key().id(),
                   "owner" : r.owner} for r in result]

        if len(rlist) == 0:
            rlist = None
            pass
        if display_all_users:
            param_map = [("all", "1")]
        else:
            param_map = []
            pass
        template_values = {
            'username' : users.get_current_user().nickname(),
            'extra_info' : extra_info,
            'extra_info_2' : extra_info_2,
            'testsets' : rlist,
            'navig' : self.get_navig_str ("/", param_map, view_index, last),
            'logout_url': users.create_logout_url("/")
            }

        if users.is_current_user_admin():
            template_values["admin"] = True
            pass

        template = jinja_environment.get_template('index.html')
        self.response.out.write(template.render(template_values))
        return
    pass


class AddTestSet(CommonPage):
    """Adding a new test set page"""

    def post(self):
        """Add the page and redirect back to main page"""

        if not self.check_user():
            return

        tsname = self.request.get("set_name").strip()
        if tsname == "":
            self.redirect("/?extra=1")
            return

        try:
            new_set = TestSet(name=tsname)
            new_set.put()
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        self.redirect('/');
        return
    pass

class RenameTestSet(CommonPage):
    """Renaming a new test set page"""

    def post(self):
        """Rename the page and redirect back to main page"""

        self.reset_common_values()
        if not self.check_user():
            self.redirect('/');
            return

        tsname = self.request.get('set_name').strip()
        if tsname == "":
            self.redirect('/?extra=1')
            return

        if (not self.get_test_set()):
            return

        try:
            self._tset.name = tsname
            self._tset.put()
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        self.redirect("/dispset?tsid=" + str(self._tsid))
        return
    pass


class DeleteTestSet(CommonPage):
    """Deleting a test set"""

    def post(self):
        """Add the page and redirect back to main page"""

        if not self.check_user():
            return

        self.reset_common_values()
        if not self.get_test_set():
            return

        conf = self.request.get("confirm")
        if conf == "yes":
            try:
                q = TestWord.all()
                q.ancestor(self._tsk)

                del_list = [r for r in q.run(keys_only=True, batch_size=100)]
                db.delete(del_list)
                self._tset.delete()
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                raise
                self.redirect("/?extra=4")
                return
            self.redirect("/")
            return
        elif conf == "no":
            self.redirect("/dispset?tsid=" + str(self._tsid))
            return

        template_values = {
            "name" : self._tset.name,
            "tsid" : self._tsid,
            "verb" : "<b>delete</b>",
            "link" : "/delset",
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url" : users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template("confsetaction.html")
        self.response.out.write(template.render(template_values))
        return
    pass

class ResetTestSet(CommonPage):
    """Reset all words in a test set"""

    def post(self):
        """Reset all words and redirect back to set page"""

        if not self.check_user():
            return

        self.reset_common_values()
        if not self.get_test_set():
            return

        conf = self.request.get("confirm")
        if conf == "yes":
            try:
                q = TestWord.all()
                q.ancestor(self._tsk)

                for w in q:
                    w.good = 0
                    w.bad = 0
                    w.test = True
                    w.put()
                    pass
                pass
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                raise
                self.redirect("/?extra=6")
                return
            self.redirect("/dispset?tsid=" + str(self._tsid))
            return
        elif conf == "no":
            self.redirect("/dispset?tsid=" + str(self._tsid))
            return

        template_values = {
            "name" : self._tset.name,
            "tsid" : self._tsid,
            "verb" : "reset",
            "link" : "/resetset",
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url" : users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template("confsetaction.html")
        self.response.out.write(template.render(template_values))
        return

class TestSetPage(CommonPage):
    """Page to manipulate a test set"""

    def produce_status(self, r):
        """Produce a note for a word r into the table"""

        if r.test:
            return "Active"
        else:
            return "Completed"
        return

    def get_first_desc_line(self, s):
        i = s.strip().find("\n")
        f = False
        if i == 0:
            return ""
        elif i > 0:
            s = s[:i]
            f = True
            pass
        elif len(s) > 35:
            s = s[:35]
            f = True
            pass
        if f:
            s = s + "..."
            pass
        return s

    def get(self):
        """Display the main page with test-set listing and manipulation."""

        if not self.check_user():
            self.redirect('/');
            return

        self.reset_common_values()
        extra_info = self.get_extra_info_string()
        view_index = self.get_view_index()

        if not self.get_test_set():
            return

        try:
            q = TestWord.all()
            q.ancestor(self._tsk)
            q.order("word")
            result = q.fetch(limit = self.items_per_page + 1,
                             offset = view_index);
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        if (len(result) > self.items_per_page):
            last = False
            result = result[:-1]
        else:
            last = True
            pass

        rlist = [ {"word" : r.word,
                   "desc" : self.get_first_desc_line(r.desc),
                   "good" : r.good,
                   "bad" : r.bad,
                   "status" : self.produce_status (r),
                   "id" : r.key().id()} for r in result]

        if len(rlist) == 0:
            rlist = None

        template_values = {
            "name": self._tset.name,
            "extra_info" : extra_info,
            "tsid" : self._tsid,
            "words" : rlist,
            "navig" : self.get_navig_str ("/dispset",
                                          [("tsid", self._tsid)],
                                          view_index, last),
            "back_url" : "/",
            "logout_url": users.create_logout_url(self.request.uri)
            }

        if self.request.get("afteredit") == "1":
            template_values["afteredit"] = True

        template = jinja_environment.get_template("dispset.html")
        self.response.out.write(template.render(template_values))
        return
    pass

class AddWord(CommonPage):
    """Adding a new word"""

    def post(self):
        """Add the page and redirect back to main page"""

        if not self.check_user():
            return

        self.reset_common_values()
        word = self.request.get('word').strip()
        desc = self.request.get("desc")
        if (word == "") or (desc.strip() == ""):
            self.redirect('/dispset?extra=1')
            return

        if not self.get_test_set():
            return

        try:
            new_word = TestWord(parent = self._tsk)
            new_word.word = word
            new_word.desc = desc
            new_word.good = 0
            new_word.bad = 0
            new_word.test = True
            new_word.put()
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        self.redirect("/dispset?tsid=" + str(self._tsid)
                      + "&amp;afteredit=1")
        return
    pass

class DeleteWord(CommonPage):
    """Deleting a word"""

    def get(self):
        """Delete a word and redirect back to set"""

        self.reset_common_values()
        if (not self.check_user()
            or not self.get_test_set_and_word_key()):
            return

        try:
            db.delete(self._wkey)
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect('/?extra=4')
            return

        self.redirect("/dispset?tsid=" + str(self._tsid))
        return
    pass

class EditWord(CommonPage):
    """Display a form for editing a word and process its results"""

    def get(self):
        """Display a page for editing a word"""

        if not self.check_user():
            return

        self.reset_common_values()
        if not self.get_test_set_and_word():
            return

        reset_flag = self.request.get("reset")
        if reset_flag == "1":
            try:
                self._word.good = 0
                self._word.bad = 0
                self._word.test = True
                self._word.put()
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                self.redirect("/?extra=6")
                return
            self.redirect("/dispset?tsid=" + str(self._tsid))
            return

        template_values = {
            'word' : self._word.word,
            'tsid' : self._tsid,
            'wid' : self._wid,
            'desc' : self._word.desc,
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url": users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template('editword.html')
        self.response.out.write(template.render(template_values))
        return

    def post(self):
        """Process a word edit"""

        if not self.check_user():
            return

        self.reset_common_values()
        if not self.get_test_set_and_word():
            return

        wordval = self.request.get('word').strip()
        desc = self.request.get("desc")
        if (wordval == "") or (desc.strip() == ""):
            self.redirect("/dispset?extra=1&amp;tsid=" + str(self._tskid))
            return

        try:
            self._word.word = wordval
            self._word.desc = desc
            self._word.good = 0
            self._word.bad = 0
            self._word.test = True
            self._word.put()
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        self.redirect("/dispset?tsid=" + str(self._tsid))
        return
    pass

class ExportTestSet(CommonPage):
    """Generate a CSV of words in the current set"""

    def write(self, s):
        self.response.out.write(s.decode("utf8"))
        return

    def post(self):
        """Generate a CSV of words in the current set"""

        if not self.check_user():
            return

        self.reset_common_values()
        if not self.get_test_set():
            return

        self.response.headers['Content-Type'] = 'text/csv'
        self.response.headers['Content-disposition'] = (("attachment;"
                                                         + "filename=%s.csv")
                                                        % str(self._tset.name))
        csv_writer = csv.writer(self)
        q = TestWord.all()
        q.ancestor(self._tsk)
        for w in q:
            csv_writer.writerow ([w.word.encode("utf8")]
                                 + w.desc.encode("utf8").splitlines())
            pass
        return
    pass

class ImportTestSet(CommonPage):
    """Import a CSV of words into the current set"""

    def do_import(self, file_contents):
        error = False
        num = 0;
        # The following decode.encode sequence is intentional and
        # necessary to load Spanish accents.
        reader = csv.reader([s.decode("utf8").encode("utf8") for s in file_contents])
        try:
            for row in reader:
                new_word = TestWord(parent = self._tsk)
                new_word.word = row[0].decode("utf8")
                new_word.desc = "\n".join(row[1:]).decode("utf8")
                new_word.good = 0
                new_word.bad = 0
                new_word.test = True
                new_word.put()

                num = num + 1
                if (num >= 200):
                    break
                pass
            pass
        except apiproxy_errors.OverQuotaError:
            error = True
            err_desc = error_mapping[5]
            pass
        except csv.Error as e:
            error = True
            err_desc = "Error on line %d: %s" % (reader.line_num, e)
            pass
        except:
            error = True
            err_desc = "Unknown error on line %d" % reader.line_num
            pass

        res = "%i words imported to the set." % num
        if error:
            res = res + "<br>\n" + err_desc

        template_values = {
            "tsetname" : self._tset.name,
            "tsid" : self._tsid,
            "result" : res,
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url": users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template("importres.html")
        self.response.out.write(template.render(template_values))
        return

    def from_url (self):
        download_error = False
        url = self.request.get("csvurl")
        try:
            csv_data = urllib2.urlopen (url)
        except urllib2.URLError as e:
            download_error = True
            err = "Error accessing the URL: %s" % e
        except apiproxy_errors.OverQuotaError:
            download_error = True
            err = error_mapping[5]
        except Exception as e:
            download_error = True
            err = "Error: " + str(e)
        except:
            download_error = True
            err = "Unknown Error accessing the URL"
            pass

        if download_error:
            template_values = {
                "tsetname" : self._tset.name,
                "tsid" : self._tsid,
                "result" : err,
                "back_url" : "/dispset?tsid=" + str(self._tsid),
                "logout_url": users.create_logout_url(self.request.uri)
                }
            template = jinja_environment.get_template("importres.html")
            self.response.out.write(template.render(template_values))
            return


        self.do_import (csv_data)
        return

    def post(self):
        """Generate a page to select method and then import thr CSV"""

        self.reset_common_values()
        if (not self.check_user()
            or not self.get_test_set()):
            return

        if self.request.get("urlsubmit") != "":
            self.from_url()
            return
        elif self.request.get("filesubmit") != "":
            file_contents = str(self.request.get("csvfile")).splitlines()
            self.do_import(file_contents)
            return

        template_values = {
            "tsetname" : self._tset.name,
            "tsid" : self._tsid,
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url": users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template("import.html")
        self.response.out.write(template.render(template_values))
        return
    pass

class TestPage(CommonPage):
    """Actual testing and answer processing"""

    @db.transactional
    def process_answer(self, wordval):
        self._word = db.get(self._wkey)
        if wordval == self._word.word:
            self._word.good = self._word.good + 1
            bad = self._word.bad
            if bad == 0:
                bad = 1
                pass

            if self._word.good >= 2*bad:
                self._word.test = False
                prev_result = (("<b>Correct!</b> Testing of the word %s "
                                + "has been completed after %i right and "
                                + "%i wrong answers")
                               % (self._word.word, self._word.good,
                                  self._word.bad))
            else:
                prev_result = (("<b>Correct!</b> The word %s now has %i "
                                + "right and %i wrong answers")
                               % (self._word.word, self._word.good,
                                  self._word.bad))
                pass
        else:
            self._word.bad = self._word.bad + 1
            prev_result = (("<b>Wrong!</b> The word <b>%s</b> now has %i "
                            + "right and %i incorrect answers")
                           % (self._word.word, self._word.good,
                              self._word.bad))
            pass
        self._word.put()
        return prev_result

    def post(self):
        """Display a new test page.  If there was an answer, process it."""

        if not self.check_user():
            return

        self.reset_common_values()
        if self.request.get("answer").strip() == "1":
            with_answer = True
            if not self.get_test_set_and_word_key():
                return

            wordval = self.request.get("wordval").strip()
            try:
                prev_result = self.process_answer(wordval)
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                with_answer = False
                prev_result = ("Could not process the previous answer "
                               + "due to transaction failure (concurrent "
                               + "access?)")
                pass
            pass
        else:
            with_answer = False
            prev_result = ""
            if not self.get_test_set():
                return
            pass
        
        try:
            q = TestWord.all()
            q.ancestor(self._tsk)
            q.filter ("test = ", True)
            c = q.count(limit=500)
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        if c == 0:
            template_values = {
                "tsetname" : self._tset.name,
                "tsid" : self._tsid,
                "back_url" : "/dispset?tsid=" + str(self._tsid),
                "logout_url": users.create_logout_url(self.request.uri)
                }
            template = jinja_environment.get_template("setcompleted.html")
            self.response.out.write(template.render(template_values))
            return

        while True:
            i = random.randint(0, c - 1)
            try:
                next_word = q.get(offset=i)
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                self.redirect("/?extra=6")
                return
            if ((not with_answer)
                or (c == 1)
                or (next_word.key().id() != self._wid)):
                break
            pass

        template_values = {
            "tsetname" : self._tset.name,
            "tsid" : self._tsid,
            "prev_result" : prev_result,
            "desc" : next_word.desc,
            "wid" : next_word.key().id(),
            "num_right" : next_word.good,
            "num_wrong" : next_word.bad,
            "back_url" : "/dispset?tsid=" + str(self._tsid),
            "logout_url": users.create_logout_url(self.request.uri)
            }
        template = jinja_environment.get_template('test.html')
        self.response.out.write(template.render(template_values))
        return

class UsersPage(CommonPage):
    """Manipulate allowed users"""

    def show(self):

        view_index = self.get_view_index()
        try:
            q = AllowedUser.all()
            result = q.fetch(limit = self.items_per_page + 1,
                             offset = view_index);
        except apiproxy_errors.OverQuotaError:
            self.redirect("/?extra=5")
            return
        except:
            self.redirect("/?extra=6")
            return

        if (len(result) > self.items_per_page):
            last = False
            result = result[:-1]
        else:
            last = True
            pass

        rlist = [ {"email" : r.email,
                   "desc" : r.desc} for r in result]
        if len(rlist) == 0:
            rlist = None
            pass

        template_values = {
            "users" : rlist,
            "navig" : self.get_navig_str ("/users", [], view_index, last),
            "back_url" : "/",
            "logout_url": users.create_logout_url("/")
            }
        
        template = jinja_environment.get_template('users.html')
        self.response.out.write(template.render(template_values))
        return

    def get(self):
        """Display the main page with test-set listing and manipulation."""

        if (not users.get_current_user()
            and users.is_current_user_admin()):
            self.redirect('/');
            return
        self.show()
        return

    def post(self):
        """Add or delete a user and then display the user page too."""

        if (not users.get_current_user()
            and users.is_current_user_admin()):
            self.redirect('/');
            return

        if self.request.get("act") == "add":
            email = self.request.get("email").strip().lower()
            desc = self.request.get("desc").strip()
            if email == "":
                self.redirect("/?extra=1")
                return
            try:
                new_user = AllowedUser(email=email, desc=desc)
                new_user.put()
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                self.redirect("/?extra=6")
                return
            pass
        elif self.request.get("act") == "delete":
            email = self.request.get("email")
            if email == "":
                self.redirect("/?extra=1")
                return
            try:
                q = AllowedUser.all()
                q.filter("email =", email)
                result = q.get(keys_only=True)
                if result != None:
                    db.delete(result)
            except apiproxy_errors.OverQuotaError:
                self.redirect("/?extra=5")
                return
            except:
                self.redirect("/?extra=4")
                return
            pass
        else:
            self.redirect("/?extra=1")            

        self.show()
        return
    pass

class HelpPage(CommonPage):
    """Display a page with help on usage on this application"""

    def get(self):
        """Display the page"""

        if not self.check_user():
            return

        template_values = {
            "back_url" : "/",
            "logout_url": users.create_logout_url("/")
            }            
        template = jinja_environment.get_template('help.html')
        self.response.out.write(template.render(template_values))
        return
    pass

class LicensePage(CommonPage):
    """Display a page with license of this application"""

    def get(self):
        """Display the page"""

        if users.get_current_user():
            template_values = {
                "back_url" : "/",
                "logout_url": users.create_logout_url("/")
                }
        else:
            template_values = {
                "back_url" : "/"
                }
            pass

        template = jinja_environment.get_template('license.html')
        self.response.out.write(template.render(template_values))
        return
    pass



app = webapp2.WSGIApplication([('/', MainPage),
                               ('/addset', AddTestSet),
                               ('/renameset', RenameTestSet),
                               ('/resetset', ResetTestSet),
                               ('/importset', ImportTestSet),
                               ('/exportset', ExportTestSet),
                               ('/delset', DeleteTestSet),
                               ('/dispset', TestSetPage),
                               ('/addword', AddWord),
                               ('/editword', EditWord),
                               ('/delword', DeleteWord),
                               ('/test', TestPage),
                               ('/help', HelpPage),
                               ('/license', LicensePage),
                               ('/users', UsersPage)],
                              debug=True)
