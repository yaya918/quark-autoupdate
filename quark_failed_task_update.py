#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克资源失效任务增量更新脚本
功能：只针对失效任务，更新已转存资源之后的新文件
"""
import os
import re
import json
import time
import requests
import urllib.parse
from datetime import datetime
from urllib.parse import unquote


class FailedTaskIncrementalUpdater:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config_data = {}
        self.quark_client = SimpleQuarkClient()
        self.api_token = "xxxxxxxxxxxxxxxx"
        self.base_url = "http://192.168.2.99:15005"

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

    def get_new_resources(self, taskname):
        """从接口获取新的资源地址"""
        try:
            encoded_taskname = urllib.parse.quote(taskname)
            url = f"{self.base_url}/task_suggestions?q={encoded_taskname}&d=1&token={self.api_token}"

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    return data['data']
                else:
                    print(f"❌ 接口返回数据格式异常")
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
            encoded_path = urllib.parse.quote(savepath)
            url = f"{self.base_url}/get_savepath_detail?path={encoded_path}&token=87e7eb745cb0d5d8"

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    return data['data']['list']
                else:
                    print(f"❌ 已转存资源接口返回数据格式异常")
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

    def check_resource_validity(self, shareurl):
        """检查资源是否有效"""
        try:
            pwd_id, passcode, pdir_fid, _ = self.quark_client.extract_url(shareurl)
            stoken_response = self.quark_client.get_stoken(pwd_id, passcode)

            if stoken_response.get("status") == 200:
                stoken = stoken_response["data"]["stoken"]
                detail_response = self.quark_client.get_detail(pwd_id, stoken, pdir_fid)

                if detail_response.get("code") == 0 and detail_response["data"]["list"]:
                    return True, "资源有效", detail_response["data"]["list"]
                else:
                    return False, "资源详情获取失败", None
            else:
                return False, stoken_response.get("message", "未知错误"), None

        except Exception as e:
            return False, f"验证过程中出错: {str(e)}", None

    def analyze_resource_structure(self, shareurl, taskname):
        """分析资源结构，获取文件夹和文件信息"""
        try:
            pwd_id, passcode, pdir_fid, _ = self.quark_client.extract_url(shareurl)
            stoken_response = self.quark_client.get_stoken(pwd_id, passcode)

            if stoken_response.get("status") == 200:
                stoken = stoken_response["data"]["stoken"]
                detail_response = self.quark_client.get_detail(pwd_id, stoken, pdir_fid)

                if detail_response.get("code") == 0:
                    file_list = detail_response["data"]["list"]

                    analysis = {
                        'url': shareurl,
                        'is_valid': True,
                        'folders': [],
                        'files': [],
                        'all_episodes': []
                    }

                    for item in file_list:
                        if item.get('dir'):
                            # 分析文件夹
                            folder_analysis = self.analyze_folder_content(item, pwd_id, stoken, taskname)
                            analysis['folders'].append(folder_analysis)
                            analysis['all_episodes'].extend(folder_analysis['episodes'])
                        else:
                            # 分析文件
                            episode = self.extract_episode_number(item.get('file_name', ''), taskname)
                            if episode is not None:
                                file_info = {
                                    'fid': item.get('fid'),
                                    'file_name': item.get('file_name'),
                                    'episode': episode,
                                    'updated_at': item.get('updated_at', 0),
                                    'is_folder': False
                                }
                                analysis['files'].append(file_info)
                                analysis['all_episodes'].append(file_info)

                    # 按剧集排序
                    analysis['all_episodes'].sort(key=lambda x: x['episode'])

                    if analysis['all_episodes']:
                        analysis['min_episode'] = min(ep['episode'] for ep in analysis['all_episodes'])
                        analysis['max_episode'] = max(ep['episode'] for ep in analysis['all_episodes'])
                        analysis['episode_count'] = len(analysis['all_episodes'])

                    return analysis
                else:
                    return {
                        'url': shareurl,
                        'is_valid': False,
                        'error': '无法获取文件列表'
                    }
            else:
                return {
                    'url': shareurl,
                    'is_valid': False,
                    'error': stoken_response.get("message", "未知错误")
                }

        except Exception as e:
            return {
                'url': shareurl,
                'is_valid': False,
                'error': f"分析过程中出错: {str(e)}"
            }

    def analyze_folder_content(self, folder_info, pwd_id, stoken, taskname):
        """分析文件夹内容"""
        folder_analysis = {
            'fid': folder_info.get('fid'),
            'folder_name': folder_info.get('file_name'),
            'episodes': [],
            'files': []
        }

        try:
            # 获取文件夹内的文件列表
            detail_response = self.quark_client.get_detail(pwd_id, stoken, folder_info.get('fid'))

            if detail_response.get("code") == 0:
                for file_info in detail_response["data"]["list"]:
                    episode = self.extract_episode_number(file_info.get('file_name', ''), taskname)
                    if episode is not None:
                        episode_info = {
                            'fid': file_info.get('fid'),
                            'file_name': file_info.get('file_name'),
                            'episode': episode,
                            'updated_at': file_info.get('updated_at', 0),
                            'folder_fid': folder_info.get('fid'),
                            'folder_name': folder_info.get('file_name'),
                            'is_folder': True
                        }
                        folder_analysis['episodes'].append(episode_info)
                        folder_analysis['files'].append(file_info)

        except Exception as e:
            print(f"分析文件夹内容出错: {e}")

        return folder_analysis

    def extract_episode_number(self, filename, taskname):
        """从文件名中提取集数"""
        # 移除任务名称，专注于提取数字
        clean_filename = unquote(filename.replace(taskname, '')).strip()

        # 多种集数匹配模式（优先级从高到低）
        patterns = [
            r'第(\d+)集', r'第(\d+)话', r'第(\d+)期',
            r'EP?(\d+)', r'(\d{2,3})\.mp4', r'(\d{2,3})\.mkv',
            r'\[(\d+)\]', r'\.(\d+)\.', r'(\d{2,3})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, clean_filename)
            if match:
                episode_num = int(match.group(1))
                # 验证集数合理性
                if 1 <= episode_num <= 500:  # 假设集数在1-500之间
                    return episode_num

        return None

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
            for file_info in saved_files:
                episode = self.extract_episode_number(file_info.get('file_name', ''), task['taskname'])
                if episode is not None:
                    saved_episodes.append(episode)

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

        for episode in range(max_saved + 1, max_saved + 10):  # 检查接下来10集
            if episode in candidate_episode_nums:
                return episode

        # 如果没有找到连续剧集，返回最大保存集数+1
        return max_saved + 1

    def generate_folder_share_url(self, base_shareurl, folder_fid, folder_name):
        """生成文件夹级别的分享链接"""
        try:
            # 从基础分享链接提取pwd_id
            pwd_id_match = re.search(r'/s/(\w+)', base_shareurl)
            if not pwd_id_match:
                return base_shareurl

            pwd_id = pwd_id_match.group(1)
            base_url = base_shareurl.split('/s/')[0]

            # 编码文件夹名称
            encoded_folder_name = urllib.parse.quote(folder_name)

            # 生成文件夹级分享链接
            folder_url = f"{base_url}/s/{pwd_id}/{folder_fid}-{encoded_folder_name}"
            return folder_url
        except Exception as e:
            print(f"生成文件夹分享链接出错: {e}")
            return base_shareurl

    def find_episode_folder(self, target_episode, resource_analysis):
        """找到特定剧集所在的文件夹"""
        for folder in resource_analysis.get('folders', []):
            for ep in folder.get('episodes', []):
                if ep['episode'] == target_episode:
                    return folder
        return None

    def select_best_resource(self, resources_analysis, taskname, saved_episodes):
        """选择最佳资源，考虑剧集连续性"""
        valid_resources = [r for r in resources_analysis if r['is_valid']]

        if not valid_resources:
            return None

        print(f"   📊 找到 {len(valid_resources)} 个有效资源，正在评估...")

        # 评分系统
        scored_resources = []

        for resource in valid_resources:
            score = 0

            # 1. 基于剧集连续性评分（50%）
            if resource['all_episodes']:
                continuation_point = self.find_continuation_point(resource['all_episodes'], saved_episodes)
                max_episode = max(ep['episode'] for ep in resource['all_episodes'])

                if continuation_point <= max_episode:
                    # 能够续播的资源得分更高
                    continuity_score = 50 * (1 - (continuation_point - 1) / max_episode)
                    score += continuity_score
                else:
                    # 不能续播的资源得分较低
                    score += 10

            # 2. 基于集数范围评分（30%）
            if resource['all_episodes']:
                max_episode = max(ep['episode'] for ep in resource['all_episodes'])
                max_all_episodes = max(
                    (max(ep['episode'] for ep in r['all_episodes']) for r in valid_resources if r['all_episodes']))

                if max_all_episodes > 0:
                    episode_score = 30 * (max_episode / max_all_episodes)
                    score += episode_score

            # 3. 基于文件组织结构评分（20%）
            if resource['folders']:
                # 有文件夹组织的资源得分更高
                folder_score = 20 * (len(resource['folders']) / max(1, len(resource['all_episodes']) / 10))
                score += min(folder_score, 20)
            else:
                # 没有文件夹组织的资源得分较低
                score += 5

            scored_resources.append((resource, score))

        # 按分数排序
        scored_resources.sort(key=lambda x: x[1], reverse=True)

        # 输出评估结果
        print("   📈 资源评估结果:")
        for i, (resource, score) in enumerate(scored_resources[:3]):
            episode_info = ""
            if resource['all_episodes']:
                min_ep = min(ep['episode'] for ep in resource['all_episodes'])
                max_ep = max(ep['episode'] for ep in resource['all_episodes'])
                episode_info = f", 集数:{min_ep}-{max_ep}"

            folder_info = ""
            if resource['folders']:
                folder_info = f", 文件夹:{len(resource['folders'])}个"

            print(f"      {i + 1}. 评分:{score:.1f}, 文件:{len(resource['all_episodes'])}个{episode_info}{folder_info}")

        best_resource = scored_resources[0][0]
        print(f"   🏆 选择最佳资源: 评分{scored_resources[0][1]:.1f}")

        return best_resource

    def update_failed_tasks_incremental(self):
        """只更新失效任务，并且只更新已转存资源之后的新文件"""
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
                print(
                    f"   💾 已转存剧集: {saved_episodes[-5:] if len(saved_episodes) > 5 else saved_episodes} (共{len(saved_episodes)}集)")

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

            # 分析所有候选资源
            resources_analysis = []
            for j, resource in enumerate(matched_resources[:5]):  # 只分析前5个匹配资源
                new_url = resource.get('shareurl')
                new_taskname = resource.get('taskname', '未知资源')

                if not new_url:
                    continue

                print(f"   🔄 分析资源 {j + 1}: {new_taskname}")

                # 分析资源结构
                analysis = self.analyze_resource_structure(new_url, taskname)
                resources_analysis.append(analysis)

                # 避免请求过快
                time.sleep(0.5)

            # 选择最佳资源
            best_resource = self.select_best_resource(resources_analysis, taskname, saved_episodes)

            if best_resource:
                # 确定续播点
                continuation_point = self.find_continuation_point(best_resource['all_episodes'], saved_episodes)

                if continuation_point > best_resource['max_episode']:
                    print(f"   ❌ 新资源没有续播剧集，无法增量更新")
                    continue

                print(f"   📺 续播点: 第{continuation_point}集")

                # 查找续播点所在的文件夹
                target_folder = self.find_episode_folder(continuation_point, best_resource)

                if target_folder:
                    # 生成文件夹级分享链接
                    optimized_url = self.generate_folder_share_url(
                        best_resource['url'],
                        target_folder['fid'],
                        target_folder['folder_name']
                    )
                    startfid = target_folder['fid']
                    print(f"   📁 使用文件夹级链接: {target_folder['folder_name']}")
                else:
                    # 如果没有找到文件夹，使用原始链接
                    optimized_url = best_resource['url']
                    # 找到续播点的文件fid
                    for ep in best_resource['all_episodes']:
                        if ep['episode'] == continuation_point:
                            startfid = ep['fid']
                            break
                    else:
                        startfid = None
                        print(f"   ⚠️ 无法找到续播点的文件ID")

                # 更新任务配置
                old_url = task['shareurl']
                task['shareurl'] = optimized_url
                task.pop('shareurl_ban', None)  # 移除失效标记
                task['last_updated'] = datetime.now().isoformat()

                # 设置startfid
                if startfid:
                    task['startfid'] = startfid

                print(f"   ✨ 已更新分享链接:")
                print(f"      旧: {old_url}")
                print(f"      新: {optimized_url}")
                if task.get('startfid'):
                    print(f"      起始点: {task['startfid']} (第{continuation_point}集)")

                # 显示新剧集详情
                new_episodes = [ep for ep in best_resource['all_episodes'] if ep['episode'] >= continuation_point]
                print(
                    f"   🆕 将转存新剧集: 第{continuation_point}-{best_resource['max_episode']}集 (共{len(new_episodes)}集)")

                updated_count += 1
            else:
                print(f"   💔 未找到合适的替代资源")

        print(f"\n📊 失效任务增量更新完成: 共更新了 {updated_count} 个任务")
        return updated_count > 0

    def run(self):
        """运行资源更新"""
        print("🚀 夸克资源失效任务增量更新脚本启动")
        print("=" * 50)

        if not self.load_config():
            return False

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


class SimpleQuarkClient:
    """简化的夸克客户端"""

    BASE_URL = "https://drive-pc.quark.cn"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"

    def _send_request(self, method, url, **kwargs):
        """发送请求"""
        headers = {
            "content-type": "application/json",
            "user-agent": self.USER_AGENT,
        }
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
            del kwargs["headers"]

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            return response
        except Exception as e:
            print(f"请求错误: {e}")
            fake_response = requests.Response()
            fake_response.status_code = 500
            fake_response._content = b'{"status": 500, "code": 1, "message": "request error"}'
            return fake_response

    def extract_url(self, url):
        """提取URL参数"""
        # pwd_id
        match_id = re.search(r"/s/(\w+)", url)
        pwd_id = match_id.group(1) if match_id else None
        # passcode
        match_pwd = re.search(r"pwd=(\w+)", url)
        passcode = match_pwd.group(1) if match_pwd else ""
        # path: fid-name
        paths = []
        matches = re.findall(r"/(\w{32})-?([^/]+)?", url)
        for match in matches:
            fid = match[0]
            name = urllib.parse.unquote(match[1]).replace("*101", "-")
            paths.append({"fid": fid, "name": name})
        pdir_fid = paths[-1]["fid"] if matches else 0
        return pwd_id, passcode, pdir_fid, paths

    def get_stoken(self, pwd_id, passcode=""):
        """获取stoken"""
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/token"
        querystring = {"pr": "ucpro", "fr": "pc"}
        payload = {"pwd_id": pwd_id, "passcode": passcode}
        response = self._send_request("POST", url, json=payload, params=querystring)
        return response.json()

    def get_detail(self, pwd_id, stoken, pdir_fid, _fetch_share=0, fetch_share_full_path=0):
        """获取资源详情"""
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/detail"
        querystring = {
            "pr": "ucpro",
            "fr": "pc",
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": pdir_fid,
            "force": "0",
            "_page": 1,
            "_size": "100",
            "_fetch_banner": "0",
            "_fetch_share": _fetch_share,
            "_fetch_total": "1",
            "_sort": "file_type:asc,updated_at:desc",
            "ver": "2",
            "fetch_share_full_path": fetch_share_full_path,
        }
        response = self._send_request("GET", url, params=querystring)
        return response.json()


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
