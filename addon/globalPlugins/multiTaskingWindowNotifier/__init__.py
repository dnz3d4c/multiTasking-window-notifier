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
		if obj.windowClassName == "MultitaskingViewFrame":
			# APP 목록 파일 열기
			with open(appListFile, "r", encoding="utf8") as f:
				appList = f.readlines()
			# 앱 목록에서 각 항목의 \N문자 제거
			for i in range(len(appList)):
				text = appList[i].strip("\n")
				# 앱 항목과 초점 객체가 일치하면 앱 항목에 해당하는 비프음 출력
				if obj.name == text:
					beepList = [
					523 , 587, 659, 699, 784, 880, 988, 1047
					]
					tones.beep(beepList[i], 50)
		nextHandler()
