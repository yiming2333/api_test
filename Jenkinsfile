pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // ========== 系统路径 ==========
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // ========== Allure 命令完整路径（不依赖 PATH）==========
        // ⚠️ 改成你实际的 allure.bat 路径
        ALLURE_CMD = 'C:/Users/27088/AppData/Roaming/npm/node_modules/allure-commandline/dist/bin/allure.bat'

        // ========== pip 依赖源 ==========
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

        // ========== Allure 报告相关 ==========
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT_DIR = 'reports/allure-report'
        ALLURE_REPORT_NAME = 'AllureReport'

        // ========== 【关键】History 固定存储目录 ==========
        // 这个目录不在 workspace 里，不会被 cleanWorkspace 清掉
        // 用 JOB_NAME 区分不同任务，防止多任务互相覆盖
        ALLURE_HISTORY_DIR = "C:/work/yss/allure-history/${env.JOB_NAME}"

        // ========== 邮件配置 ==========
        MAIL_RECIPIENT = 'yiming_2333@sina.com'

        // ========== 编码设置 ==========
        PYTHONIOENCODING = 'utf-8'

        // ========== Git 配置 ==========
        GIT_URL = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH = 'master'
        GIT_CREDENTIALS_ID = ''

        // ========== 报告链接 ==========
        REPORT_LINK = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${env.ALLURE_REPORT_NAME}/"
    }

    stages {
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户: ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(3) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        // ================================================================
        //  stage 4：生成 Allure 报告 + Trend（完善版）
        // ================================================================
        stage('4. 生成并发布 Allure 报告') {
            steps {
                script {
                    // ---------- Step 1: 确保 history 固定目录存在 ----------
                    bat """
                        if not exist "${ALLURE_HISTORY_DIR}" mkdir "${ALLURE_HISTORY_DIR}"
                    """

                    // ---------- Step 2: 从固定目录拷贝 history 到本次 results ----------
                    if (fileExists("${ALLURE_HISTORY_DIR}/history.json")) {
                        echo "✅ 找到历史 Trend 数据，正在注入..."
                        bat """
                            chcp 65001
                            if not exist "${ALLURE_RESULTS}\\history" mkdir "${ALLURE_RESULTS}\\history"
                            xcopy /E /I /Y "${ALLURE_HISTORY_DIR}\\*" "${ALLURE_RESULTS}\\history\\" >nul
                        """
                    } else {
                        echo "ℹ️ 首次构建或无历史数据，跳过 history 注入"
                    }

                    // ---------- Step 3: 生成报告（写死 allure 路径，不依赖 PATH）----------
                    try {
                        bat """
                            chcp 65001
                            "${ALLURE_CMD}" generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT_DIR}" --clean
                        """
                        echo "✅ Allure 报告生成成功"
                    } catch (e) {
                        echo "❌ Allure 报告生成失败: ${e.message}"
                        // 不 raise，让 pipeline 继续走到 publishHTML
                    }

                    // ---------- Step 4: 把新生成的 history 拷回固定目录（供下次使用）----------
                    if (fileExists("${ALLURE_REPORT_DIR}/history")) {
                        bat """
                            chcp 65001
                            xcopy /E /I /Y "${ALLURE_REPORT_DIR}\\history\\*" "${ALLURE_HISTORY_DIR}\\" >nul
                        """
                        echo "✅ History 已同步到固定目录: ${ALLURE_HISTORY_DIR}"
                    }
                }

                // ---------- Step 5: 发布 HTML 报告 ----------
                publishHTML([
                    reportDir: env.ALLURE_REPORT_DIR,
                    reportFiles: 'index.html',
                    reportName: env.ALLURE_REPORT_NAME,
                    allowMissing: true,
                    keepAll: true,
                    alwaysLinkToLastBuild: false
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            // 归档日志 + history（双保险）
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
            archiveArtifacts artifacts: 'reports/allure-report/history/**', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

// ========== 邮件发送函数（不变）==========
def sendEmailNotification(String status, String color, String icon) {
    emailext (
        to: env.MAIL_RECIPIENT,
        subject: "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body: """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}