/**
 * jobs-table view.
 *
 * Extends BaseTableView with jobs-specific row templates,
 * run/edit sub-views, and refresh/timezone controls.
 *
 * @author wenbin@nextdoor.com
 * @refactor uses base-table-view for shared DataTable lifecycle
 */

require.config({
  paths: {
    'jquery': 'vendor/jquery',
    'underscore': 'vendor/underscore',
    'backbone': 'vendor/backbone',
    'bootstrap': 'vendor/bootstrap',
    'datatables': 'vendor/jquery.dataTables',

    'utils': 'utils',
    'base-table-view': 'views/base-table-view',
    'run-job-view': 'views/jobs/run-job-view',
    'edit-job-view': 'views/jobs/edit-job-view',

    'text': 'vendor/text',
    'job-row-name': 'templates/job-row-name.html',
    'job-row-action': 'templates/job-row-action.html'
  },

  shim: {
    'bootstrap': {
      deps: ['jquery']
    },

    'backbone': {
      deps: ['underscore', 'jquery'],
      exports: 'Backbone'
    },

    'datatables': {
      deps: ['jquery'],
      exports: '$.fn.dataTable'
    }
  }
});

define(['utils',
        'base-table-view',
        'run-job-view',
        'edit-job-view',
        'text!job-row-name',
        'text!job-row-action',
        'backbone',
        'bootstrap',
        'datatables'], function(utils,
                                BaseTableView,
                                RunJobView,
                                EditJobView,
                                JobRowNameHtml,
                                JobRowActionHtml) {
  'use strict';

  return BaseTableView.extend({

    tableId: 'jobs-table',
    spinnerId: 'jobs-spinner',

    /**
     * DataTable options -- sorted by job name ascending.
     */
    dataTableOptions: function() {
      return { 'order': [[0, 'asc']] };
    },

    /**
     * Bind refresh button and timezone dropdown using safeBind
     * to prevent duplicate handlers on re-initialisation.
     */
    _bindDOMEvents: function() {
      this.safeBind('#jobs-refresh-button', 'click', this.resetRender);
      this.safeBind('#display-tz', 'change', this.resetRender);
    },

    /**
     * Re-fetch the jobs collection (used by the base reset / refresh flow).
     */
    refreshCollection: function() {
      this.collection.getJobs();
    },

    /**
     * Build row data array for DataTable from the jobs collection.
     */
    buildRows: function() {
      var jobs = this.collection.jobs;
      var data = [];

      _.each(jobs, function(job) {
        var jobObj = job.toJSON();
        data.push([
          _.template(JobRowNameHtml)({
            'job_name': _.escape(jobObj.name),
            'job_schedule': job.getScheduleString(),
            'next_run_at': job.getNextRunTimeHTMLString(),
            'job_id': jobObj.job_id,
            'job_class': _.escape(jobObj.job_class_string),
            'job_month': _.escape(jobObj.month),
            'job_day_of_week': _.escape(jobObj.day_of_week),
            'job_day': _.escape(jobObj.day),
            'job_hour': _.escape(jobObj.hour),
            'job_minute': _.escape(jobObj.minute),
            'job_active': job.getActiveString(),
            'job_pubargs': _.escape(job.getPubArgsString())
          }),
          job.getScheduleString(),
          job.getNextRunTimeHTMLString(),
          _.template(JobRowActionHtml)({
            'job_name': _.escape(jobObj.name),
            'job_id': jobObj.job_id,
            'job_class': _.escape(jobObj.job_class_string),
            'job_pubargs': _.escape(job.getPubArgsString())
          })
        ]);
      });

      return data;
    },

    /**
     * After table is rendered, set up RunJob and EditJob sub-views.
     */
    afterRender: function() {
      new RunJobView({
        collection: this.collection
      });

      new EditJobView({
        collection: this.collection
      });
    }
  });
});
