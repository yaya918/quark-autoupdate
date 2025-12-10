#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克资源失效任务增量更新脚本 - 修复版本
功能：基于文件夹结构分析，更新分享链接到最新剧集所在的文件夹
"""
import os
import re
import json
import time
import requests
import hashlib
import urllib.parse
from datetime import datetime
from urllib.parse import unquote


class FailedTaskIncrementalUpdater:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config_data = {}
        
        # 从配置文件读取webui配置并生成token
        self.load_config()
        self.api_token = self.generate_api_token()
        
        # 从环境变量获取base_url，如果没有设置则使用默认值
        self.base_url = os.getenv('QUARK_BASE_URL', 'http://127.0.0.1:5005')
        
        self.video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.rmvb']
        
        print(f"🔧 初始化配置:")
        print(f"   配置文件: {config_path}")
        print(f"   API地址: {self.base_url}")
        print(f"   API Token: {self.api_token[:8]}... (前8位)")

    def generate_api_token(self):
        """根据webui配置生成API token"""
        try:
            webui_config = self.config_data.get('webui', {})
            username = webui_config.get('username', 'admin')
            password = webui_config.get('password', 'admin12345')
            
            # 生成token的算法与webui一致
            token_string = f"token{username}{password}+-*/"
            md5_hash = hashlib.md5(token_string.encode('utf-8')).hexdigest()
            api_token = md5_hash[8:24]  # 取第8-24位
            
            print(f"✅ 根据配置文件生成API Token")
            print(f"   用户名: {username}")
            print(f"   密码: {'*' * len(password)}")
            
            return api_token
        except Exception as e:
            print(f"❌ 生成API Token失败: {e}")
            # 返回一个默认的token（如果生成失败）
            return os.getenv('QUARK_API_TOKEN', '87e7eb745cb0d5d8')

    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            print(f"✅ 配置文件加载成功: {self.config_path}")
            return True
        except Exception as e:
            print(f"❌ 配置文件加载失败: {e}")
            return False

    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 配置文件保存成功: {self.config_path}")
            return True
        except Exception as e:
            print(f"❌ 配置保存失败: {e}")
            return False

    def trigger_resource_update(self):
        """触发资源更新脚本"""
        try:
            url = f"{self.base_url}/run_script_now?token={self.api_token}"
            params = {"token": self.api_token}
            headers = {
                "Content-Type": "application/json"
            }

            print("🔄 触发资源更新脚本...")
            response = requests.post(url, json={}, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print("✅ 资源更新脚本触发成功")
                    return True
                else:
                    print(f"❌ 资源更新脚本返回错误: {result.get('message', '未知错误')}")
                    return False
            else:
                print(f"❌ 资源更新脚本请求失败，状态码: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            print("❌ 资源更新脚本请求超时")
            return False
        except Exception as e:
            print(f"❌ 触发资源更新脚本时出错: {e}")
            return False

    def get_new_resources(self, taskname):
        """从接口获取新的资源地址"""
        try:
            #encoded_taskname = urllib.parse.quote(taskname)
            url = f"{self.base_url}/task_suggestions"
            params = {
                "q": taskname,
                "d": 1,
                "token": self.api_token
            }

            response = requests.get(url, params=params, timeout=100)
            if response.status_code == 200:
                data = response.json()
                print(f"完整请求URL: {response.url}")
                if data.get('success'):
                    # print(data['data'])
                    return data['data']
                else:
                    print(f"❌ 接口返回数据格式异常: {data}")
                    return None
            else:
                print(f"❌ 接口请求失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ 获取新资源时出错: {e}")
            return None

    def get_saved_resources(self, savepath):
        """通过API获取已转存的资源列表"""
        try:
            # URL编码保存路径
            # encoded_path = urllib.parse.quote(savepath)
            url = f"{self.base_url}/get_savepath_detail"
            params = {
                "path": savepath,
                "token": self.api_token
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    return data['data']['list']
                else:
                    print(f"❌ 已转存资源接口返回数据格式异常: {data}")
                    return None
            else:
                print(f"❌ 已转存资源接口请求失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ 获取已转存资源时出错: {e}")
            return None

    def is_taskname_match(self, candidate_taskname, original_taskname):
        """判断候选任务名是否与原始任务名匹配"""

        def clean_name(name):
            name = re.sub(r'[【】\[\]\(\)（）]', '', name)
            name = re.sub(r'\s+', '', name)
            return name.lower()

        clean_candidate = clean_name(candidate_taskname)
        clean_original = clean_name(original_taskname)

        # 检查候选任务名是否包含原始任务名
        if clean_original in clean_candidate:
            return True

        # 检查是否是同一内容的不同表述
        common_patterns = [
            (r'绝世唐门', r'绝世唐门'),
            (r'斗罗大陆2', r'斗罗大陆2'),
            (r'斗罗大陆Ⅱ', r'斗罗大陆2'),
            (r'第(\d+)季', r'第\1季'),
        ]

        for pattern_orig, pattern_cand in common_patterns:
            if re.search(pattern_orig, clean_original) and re.search(pattern_cand, clean_candidate):
                return True

        return False

    def is_video_file(self, filename):
        """检查是否是视频文件"""
        return any(filename.lower().endswith(ext) for ext in self.video_extensions)

    def extract_episode_number_enhanced(self, filename, taskname):
        """从文件名中提取集数 - 增强版"""
        # 移除任务名称
        clean_filename = unquote(filename).replace(taskname, '').strip()

        # 多种集数匹配模式（优先级从高到低）
        patterns = [
            # S05E171 格式 (季 Episode)
            r'S\d+E(\d+)',
            r's\d+e(\d+)',
            r'[Ss]\d+[Ee](\d+)',

            # 中文格式
            r'第(\d+)集', r'第(\d+)话', r'第(\d+)期',

            # EP格式
            r'EP?(\d+)',

            # 数字格式
            r'\.(\d{2,4})\.',  # 匹配 .114. 这种格式
            r'(\d{2,4})\.mp4', r'(\d{2,4})\.mkv', r'(\d{2,4})\.avi',
            r'\[(\d+)\]',
            r'\s(\d{2,4})\s',  # 匹配空格分隔的数字
            r'^(\d{2,4})$'  # 纯数字文件名
        ]

        for pattern in patterns:
            match = re.search(pattern, clean_filename)
            if match:
                try:
                    episode_num = int(match.group(1))
                    # 验证集数合理性
                    if 1 <= episode_num <= 2000:
                        return episode_num
                except ValueError:
                    continue

        # 如果以上模式都不匹配，尝试更宽松的数字提取
        numbers = re.findall(r'\d{3,4}', clean_filename)  # 只匹配3-4位数字
        for num in numbers:
            episode_num = int(num)
            if 50 <= episode_num <= 2000:  # 针对你的114集情况
                return episode_num

        return None

    def get_share_detail(self, share_url):
        """获取分享链接详情 - 基于test1.py优化"""
        url = f"{self.base_url}/get_share_detail"
        params = {"token": self.api_token}
        payload = {"shareurl": share_url}

        try:
            response = requests.post(url, params=params, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return result["data"]
            else:
                print(f"获取分享详情失败: {result}")
                return None

        except Exception as e:
            print(f"请求失败: {e}")
            return None

    def build_share_url(self, base_share_url, fid_path=None):
        """构建包含路径的分享URL - 基于test1.py优化"""
        if fid_path is None:
            return base_share_url

        # # 从基础分享URL中提取分享ID
        # if base_share_url.startswith("https://pan.quark.cn/s/"):
        #     share_id = base_share_url.split("/")[-1]
        # else:
        #     # 如果已经是带路径的URL，提取基础部分
        #     if "#" in base_share_url:
        #         base_part = base_share_url.split("#")[0]
        #         share_id = base_part.split("/")[-1]
        #         print(base_part)
        #     else:
        #         share_id = base_share_url.split("/")[-1]
        if "#" in base_share_url:
            base_part = base_share_url.split("#")[0]
            #share_id = base_part.split("/")[-1]
            
        else:
            #share_id = base_share_url.split("/")[-1]
            base_part = base_share_url.split("/")[:-1]
        # 构建带路径的URL
        # path_part = "/".join(fid_path)
        print(base_part)
        path_part = fid_path[-1]
        return f"{base_part}#/list/share/{path_part}"

    def analyze_resource_structure_optimized(self, share_url, taskname):
        """优化版资源结构分析 - 基于test1.py的完整文件夹遍历"""
        print(f"   🔍 开始深度分析资源结构: {share_url}")

        # 获取分享详情
        share_data = self.get_share_detail(share_url)
        if not share_data:
            return {
                'url': share_url,
                'is_valid': False,
                'error': '获取分享详情失败'
            }

        share_info = share_data.get("share", {})
        print(f"   📋 分享标题: {share_info.get('title', '未知')}")
        print(f"   📁 文件数量: {share_info.get('all_file_num', share_info.get('file_num', 0))}")

        analysis = {
            'url': share_url,
            'is_valid': True,
            'folders': [],
            'files': [],
            'all_episodes': [],
            'folder_episodes': {},  # 记录每个文件夹的剧集
            'share_info': share_info,
            'full_path': share_data.get('full_path', []),
            'file_list': share_data.get('list', [])
        }

        # 开始递归遍历
        current_items = share_data.get("list", [])
        full_path = share_data.get("full_path", [])

        print(f"   🔄 开始递归遍历文件夹结构...")
        self.recursive_analyze_folders(share_url, full_path, current_items, taskname, analysis, 0)

        # 统计结果
        episode_count = len(analysis['all_episodes'])
        print(f"   ✅ 分析完成: 共找到 {episode_count} 个剧集")

        if episode_count > 0:
            # 计算最大最小集数
            episodes = [ep['episode'] for ep in analysis['all_episodes']]
            analysis['min_episode'] = min(episodes)
            analysis['max_episode'] = max(episodes)
            print(f"   📊 剧集范围: 第{analysis['min_episode']}集 - 第{analysis['max_episode']}集")

        return analysis

    def recursive_analyze_folders(self, base_share_url, current_path, items, taskname, analysis, depth):
        """递归分析文件夹结构 - 基于test1.py优化"""
        indent = "  " * depth

        # 分离文件和文件夹
        files = [item for item in items if item.get("file", False)]
        directories = [item for item in items if item.get("dir", False)]

        current_folder_episodes = []

        # 分析当前目录的视频文件
        video_files = [f for f in files if self.is_video_file(f.get("file_name", ""))]
        if video_files:
            print(f"{indent}   🎬 发现 {len(video_files)} 个视频文件")

            for file_item in video_files:
                filename = file_item.get("file_name", "")
                episode = self.extract_episode_number_enhanced(filename, taskname)

                if episode is not None:
                    file_data = {
                        'fid': file_item.get('fid'),
                        'file_name': filename,
                        'episode': episode,
                        'pdir_fid': file_item.get('pdir_fid'),
                        'size': file_item.get('size', 0),
                        'is_folder': False,
                        'folder_path': [item.get('file_name') for item in current_path],
                        'folder_fids': [item.get('fid') for item in current_path]
                    }

                    analysis['files'].append(file_data)
                    analysis['all_episodes'].append(file_data)
                    current_folder_episodes.append(file_data)

                    print(f"{indent}     ├─ {filename} - 第{episode}集")

        # 记录当前文件夹的剧集信息
        if current_folder_episodes:
            folder_key = "/".join([item.get('file_name', '') for item in current_path]) or "根目录"
            analysis['folder_episodes'][folder_key] = {
                'episodes': current_folder_episodes,
                'min_episode': min(ep['episode'] for ep in current_folder_episodes),
                'max_episode': max(ep['episode'] for ep in current_folder_episodes),
                'folder_path': current_path,
                'share_url': base_share_url
            }

        # 递归处理子文件夹
        if directories:
            print(f"{indent}   📁 发现 {len(directories)} 个子文件夹，继续分析...")

            for dir_item in directories[:3]:  # 限制分析前3个子文件夹以避免过度请求
                dir_name = dir_item.get("file_name", "未知")
                dir_fid = dir_item.get("fid", "")

                print(f"{indent}     └─ 分析文件夹: {dir_name}")

                # 构建新的路径
                new_path = current_path + [dir_item]
                fid_path = [item.get("fid") for item in new_path]
                #print(new_path)
                #print(fid_path)
                # 构建新的分享URL
                #new_share_url = self.build_share_url(base_share_url, fid_path)
                # print(new_share_url)
                    # 检查是否是第一种情况（没有#/list/share/部分）
                if "#/list/share/" not in base_share_url:
                    # 如果是基本链接，直接添加#/list/share/{fid}
                    if base_share_url.startswith(base_share_url):
                        new_share_url=f"{base_share_url}#/list/share/{fid_path[-1]}"
                    else:
                        # 如果不是标准链接，可能需要更复杂的处理
                        # 这里保持原样，但你可以根据实际情况调整
                        new_share_url=url
                elif "#/list/share/" in base_share_url:
                
                    # 第二种情况：已经有#/list/share/部分
                    # 分割链接，获取#之前的部分
                    parts = base_share_url.split("#/list/share/")
                    if len(parts) >= 2:
                        # 保留#之前的部分，替换fid
                        new_share_url=f"{parts[0]}#/list/share/{fid_path[-1]}"



                # new_share_url = f"{base_share_url}#/list/share/{fid_path[-1]}"
                print(base_share_url)
                # 获取子目录内容
                sub_dir_data = self.get_share_detail(new_share_url)
                if sub_dir_data:
                    sub_items = sub_dir_data.get("list", [])
                    self.recursive_analyze_folders(new_share_url, new_path, sub_items, taskname, analysis, depth + 1)
                else:
                    print(f"{indent}       ❌ 获取子目录失败")

                # 避免请求过快
                time.sleep(1)

    def get_saved_episodes(self, task):
        """通过API获取已保存的剧集信息"""
        try:
            savepath = task.get('savepath', '')
            if not savepath:
                return []

            # 通过API获取已转存资源列表
            saved_files = self.get_saved_resources(savepath)
            if not saved_files:
                return []

            saved_episodes = []
            # print(saved_files)
            for file_info in saved_files:
                episode = self.extract_episode_number_enhanced(file_info.get('file_name', ''), task['taskname'])
                if episode is not None:
                    saved_episodes.append(episode)
                #saved_episodes.append(file_info)

            return sorted(saved_episodes)
        except Exception as e:
            print(f"获取已保存剧集出错: {e}")
            return []

    def find_continuation_point(self, candidate_episodes, saved_episodes):
        """找到剧集连续性的断点"""
        if not saved_episodes:
            return 1  # 如果没有保存的剧集，从第1集开始

        max_saved = max(saved_episodes)

        # 检查候选资源中是否有下一集
        candidate_episode_nums = [ep['episode'] for ep in candidate_episodes]

        # 首先尝试找连续剧集
        for episode in range(max_saved + 1, max_saved + 10):  # 检查接下来10集
            if episode in candidate_episode_nums:
                return episode

        # 如果没有找到连续剧集，检查是否有比当前更大的剧集
        larger_episodes = [ep for ep in candidate_episode_nums if ep > max_saved]
        if larger_episodes:
            next_episode = min(larger_episodes)
            return next_episode

        # 如果都没有，返回最大保存集数+1
        return max_saved + 1

    def select_best_folder_for_continuation(self, resource_analysis, saved_episodes):
    ##"""选择包含续播点的最佳文件夹 - 优化版本"""
        if not resource_analysis.get('folder_episodes'):
            print(f"      ❌ 该资源没有可用的文件夹剧集信息")
            return None, None

        max_saved = max(saved_episodes) if saved_episodes else 0
        continuation_point = max_saved + 1

        print(f"   🎯 寻找包含第{continuation_point}集的最佳文件夹...")

        best_folder_info = None
        best_score = -1
        best_episode_gap = float('inf')  # 与目标集数的差距

        for folder_name, folder_info in resource_analysis['folder_episodes'].items():
            folder_episodes = [ep['episode'] for ep in folder_info['episodes']]
            min_ep = folder_info['min_episode']
            max_ep = folder_info['max_episode']

            # 计算与目标集数的差距
            if continuation_point in folder_episodes:
                episode_gap = 0  # 完美匹配
            elif continuation_point < min_ep:
                episode_gap = min_ep - continuation_point  # 文件夹起始集晚于目标
            elif continuation_point > max_ep:
                episode_gap = continuation_point - max_ep  # 文件夹结束集早于目标
            else:
                episode_gap = 0  # 在范围内但不是具体集数

            # 评分系统
            score = 0

            # 1. 是否包含续播点（最高优先级）
            if continuation_point in folder_episodes:
                score += 200  # 增加权重
                print(f"     ✅ {folder_name}: 完美匹配续播点第{continuation_point}集")

            # 2. 与续播点的接近程度
            if min_ep <= continuation_point <= max_ep:
                # 目标集数在文件夹范围内
                score += 100
                # 范围内有剧集越多越好
                score += min(len([ep for ep in folder_episodes if ep >= continuation_point]), 20)
            elif continuation_point < min_ep:
                # 文件夹起始集晚于目标，差距越小越好
                gap = min_ep - continuation_point
                if gap <= 5:  # 差距在5集以内
                    score += 80 - gap * 10
                    print(f"     ⚠️  {folder_name}: 最接近续播点，从第{min_ep}集开始（差{gap}集）")
            elif continuation_point > max_ep:
                # 文件夹结束集早于目标，尽量选择结束集最大的
                gap = continuation_point - max_ep
                if gap <= 10:  # 差距在10集以内
                    score += 60 - gap * 5

            # 3. 剧集数量（但避免包含大量过时剧集的文件夹）
            episode_count = len(folder_episodes)
            # 只计算接近目标集数的剧集数量
            relevant_episodes = len([ep for ep in folder_episodes if ep >= continuation_point - 10])
            score += min(relevant_episodes * 3, 30)

            # 4. 文件夹深度（浅层文件夹优先）
            depth_penalty = len(folder_info['folder_path']) * 3
            score -= depth_penalty

            # 如果与目标集数差距更小，优先选择
            if episode_gap < best_episode_gap or (episode_gap == best_episode_gap and score > best_score):
                best_episode_gap = episode_gap
                best_score = score
                best_folder_info = folder_info

        if best_folder_info:
            folder_name = "/".join([item.get('file_name', '') for item in best_folder_info['folder_path']]) or "根目录"
            print(f"   🏆 选择文件夹: {folder_name}")
            print(f"     剧集范围: 第{best_folder_info['min_episode']}集 - 第{best_folder_info['max_episode']}集")
            print(f"     与目标集数差距: {best_episode_gap}集")
            print(f"     评分: {best_score:.1f}")
            return best_folder_info, best_episode_gap

        print(f"   ❌ 未找到包含续播点的合适文件夹")
        return None, None



    def select_best_resource(self, resources_analysis, taskname, saved_episodes):
        #"""选择最佳资源 - 优化版，考虑文件夹结构"""
        valid_resources = [r for r in resources_analysis if r['is_valid'] and r['all_episodes']]

        if not valid_resources:
            print(f"   ❌ 没有找到包含剧集的有效资源")
            return None

        print(f"   📊 找到 {len(valid_resources)} 个包含剧集的有效资源，正在评估...")

        # 获取最大保存集数
        max_saved = max(saved_episodes) if saved_episodes else 0

        best_resource = None
        best_folder = None
        best_continuation_point = max_saved + 1
        best_episode_gap = float('inf')
        best_score = -1

        for resource in valid_resources:
            # 为每个资源选择最佳文件夹
            best_folder_for_resource, episode_gap = self.select_best_folder_for_continuation(resource, saved_episodes)

            if not best_folder_for_resource:
                continue

            # 计算资源评分（主要基于文件夹评分）
            folder_episodes = [ep['episode'] for ep in best_folder_for_resource['episodes']]
            min_ep = best_folder_for_resource['min_episode']
            max_ep = best_folder_for_resource['max_episode']
            
            score = 0
            
            # 1. 与目标集数的接近程度（最重要）
            if best_continuation_point in folder_episodes:
                score += 300
            elif min_ep <= best_continuation_point <= max_ep:
                score += 200
            else:
                # 距离目标集数越近，分数越高
                distance = min(abs(min_ep - best_continuation_point), abs(max_ep - best_continuation_point))
                if distance <= 10:
                    score += 150 - distance * 10
            
            # 2. 剧集连续性（检查是否有连续剧集）
            if min_ep <= best_continuation_point <= max_ep:
                # 计算从目标集数开始的连续剧集数量
                continuous_count = 0
                current = best_continuation_point
                while current in folder_episodes:
                    continuous_count += 1
                    current += 1
                score += min(continuous_count * 5, 50)
            
            # 3. 总剧集数量（但只考虑目标集数之后的）
            future_episodes = len([ep for ep in folder_episodes if ep >= best_continuation_point])
            score += min(future_episodes * 2, 40)
            
            # 4. 优先选择剧集较新的资源
            score += min(max_ep / 10, 20)

            # 优先选择剧集差距小的，分数相同的情况下
            if (episode_gap < best_episode_gap or 
                (episode_gap == best_episode_gap and score > best_score)):
                best_episode_gap = episode_gap
                best_score = score
                best_resource = resource
                best_folder = best_folder_for_resource

        if best_resource and best_folder:
            print(f"   🏆 选择最佳资源:")
            print(f"     评分: {best_score:.1f}")
            print(f"     最佳文件夹剧集: 第{best_folder['min_episode']}集 - 第{best_folder['max_episode']}集")
            print(f"     与目标集数差距: {best_episode_gap}集")

            # 计算实际的起始点
            folder_episodes = [ep['episode'] for ep in best_folder['episodes']]
            if best_continuation_point in folder_episodes:
                start_episode = best_continuation_point
            else:
                # 选择文件夹中最接近目标集数的剧集
                larger_episodes = [ep for ep in folder_episodes if ep >= best_continuation_point]
                if larger_episodes:
                    start_episode = min(larger_episodes)
                else:
                    start_episode = max(folder_episodes)  # 如果没有更大的，选择最新的
            
            # 将最佳文件夹信息添加到资源中
            best_resource['best_folder'] = best_folder
            best_resource['continuation_point'] = start_episode

        return best_resource

    def update_failed_tasks_incremental(self):
        """只更新失效任务，并且更新到最新剧集所在的文件夹"""
        if not self.config_data.get('tasklist'):
            print("❌ 配置文件中没有任务列表")
            return False

        # 找出所有失效任务
        failed_tasks = []
        for i, task in enumerate(self.config_data['tasklist']):
            if task.get('shareurl_ban'):
                failed_tasks.append((i, task))

        if not failed_tasks:
            print("🎉 没有发现失效任务")
            return False

        print(f"🔍 发现 {len(failed_tasks)} 个失效任务，开始增量更新...")

        updated_count = 0

        for i, (index, task) in enumerate(failed_tasks, 1):
            taskname = task.get('taskname', '未知任务')
            print(f"\n[{i}/{len(failed_tasks)}] 更新失效任务: {taskname}")
            print(f"   ⚠️ 失效原因: {task['shareurl_ban']}")

            # 获取已保存的剧集信息
            saved_episodes = self.get_saved_episodes(task)
            if saved_episodes:
                print(f"   💾 已转存剧集: {saved_episodes} (共{len(saved_episodes)}集)")

            print(f"   🔍 正在寻找新的资源地址...")

            # 获取新的资源列表
            new_resources = self.get_new_resources(taskname)
            if not new_resources:
                print(f"   ❌ 未找到新的资源地址")
                continue

            # 过滤匹配的任务名
            matched_resources = []
            for resource in new_resources:
                candidate_taskname = resource.get('taskname', '')
                if candidate_taskname and self.is_taskname_match(candidate_taskname, taskname):
                    matched_resources.append(resource)

            if not matched_resources:
                print(f"   ❌ 未找到任务名匹配的资源")
                continue

            print(f"   ✅ 找到 {len(matched_resources)} 个任务名匹配的资源")

            # 使用优化版分析所有候选资源
            resources_analysis = []
            analysis_count = min(len(matched_resources), 10)  # 限制分析数量

            for j, resource in enumerate(matched_resources[:analysis_count]):
                new_url = resource.get('shareurl')
                new_taskname = resource.get('taskname', '未知资源')

                if not new_url:
                    continue

                print(f"   🔄 分析资源 {j + 1}/{analysis_count}: {new_taskname}")

                # 使用优化的深度分析方法
                analysis = self.analyze_resource_structure_optimized(new_url, taskname)
                resources_analysis.append(analysis)

                # 避免请求过快
                time.sleep(2)

            # 选择最佳资源（考虑文件夹结构）
            best_resource = self.select_best_resource(resources_analysis, taskname, saved_episodes)

            if best_resource and best_resource.get('best_folder'):
                best_folder = best_resource['best_folder']
                continuation_point = best_resource['continuation_point']

                # 使用最佳文件夹的分享链接
                optimized_url = best_folder['share_url']

                # 查找起始文件ID（续播点剧集）
                startfid = None
                for ep in best_folder['episodes']:
                    if ep['episode'] == continuation_point:
                        startfid = ep.get('fid')
                        break

                if not startfid and best_folder['episodes']:
                    # 如果没有找到精确匹配，使用文件夹中最接近的剧集
                    closest_episode = None
                    min_gap = float('inf')
                    for ep in best_folder['episodes']:
                        gap = abs(ep['episode'] - continuation_point)
                        if gap < min_gap:
                            min_gap = gap
                            closest_episode = ep['episode']
                            startfid = ep.get('fid')

                # 更新任务配置
                old_url = task['shareurl']
                task['shareurl'] = optimized_url
                task.pop('shareurl_ban', None)  # 移除失效标记
                task['last_updated'] = datetime.now().isoformat()

                # 设置startfid
                if startfid:
                    task['startfid'] = startfid

                print(f"   ✨ 已更新分享链接到最佳文件夹:")
                print(f"      旧链接: {old_url}")
                print(f"      新链接: {optimized_url}")
                folder_path_str = "/".join([item.get('file_name', '') for item in best_folder['folder_path']]) or "根目录"
                print(f"      文件夹: {folder_path_str}")
                print(f"      起始点: {task.get('startfid', '未设置')} (第{continuation_point}集)")
                print(f"      剧集范围: 第{best_folder['min_episode']}集 - 第{best_folder['max_episode']}集")

                updated_count += 1
            else:
                print(f"   💔 未找到包含续播点的合适文件夹")

        print(f"\n📊 失效任务增量更新完成: 共更新了 {updated_count} 个任务")

        # 如果成功更新了任务，触发资源更新
        if updated_count > 0:
            print(f"\n🚀 触发资源更新脚本...")
            if self.trigger_resource_update():
                print("✅ 已成功触发资源更新")
            else:
                print("⚠️ 资源更新脚本触发失败，但任务配置已更新")

        return updated_count > 0

    def run(self):
        """运行资源更新"""
        print("🚀 夸克资源失效任务增量更新脚本启动（修复版）")
        print("=" * 50)

        if not self.load_config():
            return False

        # 检查是否有任务列表
        if not self.config_data.get('tasklist'):
            print("ℹ️ 配置文件中没有任务列表，无需更新")
            return True

        has_updates = self.update_failed_tasks_incremental()

        if has_updates:
            if self.save_config():
                print(f"\n🎉 配置已更新，请重新运行夸克自动转存脚本")
                return True
            else:
                print(f"\n❌ 配置保存失败")
                return False
        else:
            print(f"\nℹ️ 没有需要更新的任务")
            return True


def main():
    """主函数"""
    import sys

    # 配置文件路径
    config_path = sys.argv[1] if len(sys.argv) > 1 else "quark_config.json"

    # 创建更新器并运行
    updater = FailedTaskIncrementalUpdater(config_path)
    success = updater.run()

    if success:
        print("✅ 脚本执行完成")
        sys.exit(0)
    else:
        print("❌ 脚本执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()