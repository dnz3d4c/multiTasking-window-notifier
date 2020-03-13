# -*- coding: utf-8 -*-
# multiTasking window notifier

#Copyright (C) 2020 dnz3d4c <advck1123 at gmail dot com>

#This file is covered by the GNU General Public License.
#See the file COPYING for more details.



import api
import globalPluginHandler
import tones
import scriptHandler
from scriptHandler import script
import wx
import windowUtils
import ui



class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def event_gainFocus (self, obj, nextHandler):
		obj = api.getFocusObject()
		appList = [
		"제목 없음 - Windows 메모장",
		"홈 \/ 트위터 \- Mozilla Firefox",
		"addons"
		]
		if obj.windowClassName == "MultitaskingViewFrame":
			for i in range(len(appList)):
				if obj.name == appList[i]:
					tones.beep(650,60)
		nextHandler()


