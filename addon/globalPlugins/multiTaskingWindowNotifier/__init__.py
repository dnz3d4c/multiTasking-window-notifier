# -*- coding: utf-8 -*-
# multiTasking window notifier

#Copyright (C) 2020 dnz3d4c <advck1123 at gmail dot com>

#This file is covered by the GNU General Public License.
#See the file COPYING for more details.



import api
import globalPluginHandler
import globalVars
import tones
import scriptHandler
from scriptHandler import script
import os
import wx
import ui



class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	# 추가 기능 기본 변수
	configPath = globalVars.appArgs.configPath
	global appListFile
	appListFile = os.path.join(configPath, "addons", "multiTaskingWindowNotifier", "globalPlugins", "multiTaskingWindowNotifier") + "\\app.list"


	def event_gainFocus (self, obj, nextHandler):
		obj = api.getFocusObject()
		appList = [
		"제목 없음 - Windows 메모장",
		"홈 \/ 트위터 \- Mozilla Firefox",
		"addons"
		]
		beepList = [
		523 , 587, 659, 699, 784, 880, 988, 1047
		]
		if obj.windowClassName == "MultitaskingViewFrame":
			for i in range(len(appList)):
				if obj.name == appList[i]:
					tones.beep(beepList[i], 100)
		nextHandler()


